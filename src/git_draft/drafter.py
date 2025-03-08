from __future__ import annotations

import dataclasses
from datetime import datetime
import json
import logging
import os
import os.path as osp
from pathlib import PurePosixPath
import re
import textwrap
import time
from typing import Match, Sequence

import git

from .bots import Bot, Goal
from .common import JSONObject, Table, qualified_class_name, random_id
from .prompt import PromptRenderer, TemplatedPrompt
from .store import Store, sql
from .toolbox import StagingToolbox, ToolVisitor


_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _Branch:
    """Draft branch"""

    _pattern = re.compile(r"draft/(.+)")

    suffix: str

    @property
    def name(self) -> str:
        return f"draft/{self.suffix}"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def active(cls, repo: git.Repo, name: str | None = None) -> _Branch | None:
        match: Match | None = None
        if name or not repo.head.is_detached:
            match = cls._pattern.fullmatch(name or repo.active_branch.name)
        if not match:
            if name:
                raise ValueError(f"Not a valid draft branch name: {name!r}")
            return None
        return _Branch(match[1])

    @staticmethod
    def new_suffix():
        return random_id(9)


class Drafter:
    """Draft state orchestrator"""

    def __init__(self, store: Store, repo: git.Repo) -> None:
        with store.cursor() as cursor:
            cursor.executescript(sql("create-tables"))
        self._store = store
        self._repo = repo

    @classmethod
    def create(cls, store: Store, path: str | None = None) -> Drafter:
        try:
            return cls(store, git.Repo(path, search_parent_directories=True))
        except git.NoSuchPathError:
            raise ValueError(f"No git repository at {path}")

    def generate_draft(
        self,
        prompt: str | TemplatedPrompt,
        bot: Bot,
        bot_name: str | None = None,
        tool_visitors: Sequence[ToolVisitor] | None = None,
        reset: bool = False,
        sync: bool = False,
        timeout: float | None = None,
    ) -> str:
        if isinstance(prompt, str) and not prompt.strip():
            raise ValueError("Empty prompt")
        if self._repo.is_dirty(working_tree=False):
            if not reset:
                raise ValueError("Please commit or reset any staged changes")
            self._repo.index.reset()

        branch = _Branch.active(self._repo)
        if branch:
            self._stage_changes(sync)
            _logger.debug("Reusing active branch %s.", branch)
        else:
            branch = self._create_branch(sync)
            _logger.debug("Created branch %s.", branch)

        operation_recorder = _OperationRecorder()
        tool_visitors = [operation_recorder] + list(tool_visitors or [])
        toolbox = StagingToolbox(self._repo, tool_visitors)
        if isinstance(prompt, TemplatedPrompt):
            template: str | None = prompt.template
            renderer = PromptRenderer.for_toolbox(toolbox)
            prompt_contents = renderer.render(prompt)
        else:
            template = None
            prompt_contents = prompt

        with self._store.cursor() as cursor:
            [(prompt_id,)] = cursor.execute(
                sql("add-prompt"),
                {
                    "branch_suffix": branch.suffix,
                    "template": template,
                    "contents": prompt_contents,
                },
            )

        _logger.debug("Running bot... [bot=%s]", bot)
        start_time = time.perf_counter()
        goal = Goal(prompt_contents, timeout)
        action = bot.act(goal, toolbox)
        end_time = time.perf_counter()
        walltime = end_time - start_time
        _logger.info("Completed bot action. [action=%s]", action)

        toolbox.trim_index()
        title = action.title
        if not title:
            title = _default_title(prompt_contents)
        commit = self._repo.index.commit(
            f"draft! {title}\n\n{prompt_contents}",
            skip_hooks=True,
        )

        with self._store.cursor() as cursor:
            cursor.execute(
                sql("add-action"),
                {
                    "commit_sha": commit.hexsha,
                    "prompt_id": prompt_id,
                    "bot_name": bot_name,
                    "bot_class": qualified_class_name(bot.__class__),
                    "walltime": walltime,
                },
            )
            cursor.executemany(
                sql("add-operation"),
                [
                    {
                        "commit_sha": commit.hexsha,
                        "tool": o.tool,
                        "reason": o.reason,
                        "details": json.dumps(o.details),
                        "started_at": o.start,
                    }
                    for o in operation_recorder.operations
                ],
            )

        _logger.info("Generated %s.", branch)
        return str(branch)

    def finalize_draft(self, clean=False, delete=False) -> str:
        name = self._exit_draft(revert=False, clean=clean, delete=delete)
        _logger.info("Finalized %s.", name)
        return name

    def revert_draft(self, delete=False) -> str:
        name = self._exit_draft(revert=True, clean=False, delete=delete)
        _logger.info("Reverted %s.", name)
        return name

    def history_table(self, branch_name: str | None = None) -> Table:
        path = self._repo.working_dir
        branch = _Branch.active(self._repo, branch_name)
        if branch:
            with self._store.cursor() as cursor:
                results = cursor.execute(
                    sql("list-prompts"),
                    {
                        "repo_path": path,
                        "branch_suffix": branch.suffix,
                    },
                )
                return Table.from_cursor(results)
        else:
            with self._store.cursor() as cursor:
                results = cursor.execute(
                    sql("list-drafts"), {"repo_path": path}
                )
                return Table.from_cursor(results)

    def _create_branch(self, sync: bool) -> _Branch:
        if self._repo.head.is_detached:
            raise RuntimeError("No currently active branch")
        origin_branch = self._repo.active_branch.name
        origin_sha = self._repo.commit().hexsha

        self._repo.git.checkout(detach=True)
        sync_sha = self._stage_changes(sync)
        suffix = _Branch.new_suffix()

        with self._store.cursor() as cursor:
            cursor.execute(
                sql("add-branch"),
                {
                    "suffix": suffix,
                    "repo_path": self._repo.working_dir,
                    "origin_branch": origin_branch,
                    "origin_sha": origin_sha,
                    "sync_sha": sync_sha,
                },
            )

        branch = _Branch(suffix)
        branch_ref = self._repo.create_head(branch.name)
        self._repo.git.checkout(branch_ref)
        return branch

    def _stage_changes(self, sync: bool) -> str | None:
        self._repo.git.add(all=True)
        if not sync or not self._repo.is_dirty(untracked_files=True):
            return None
        ref = self._repo.index.commit("draft! sync")
        return ref.hexsha

    def _exit_draft(self, *, revert: bool, clean: bool, delete: bool) -> str:
        branch = _Branch.active(self._repo)
        if not branch:
            raise RuntimeError("Not currently on a draft branch")

        with self._store.cursor() as cursor:
            rows = cursor.execute(
                sql("get-branch-by-suffix"), {"suffix": branch.suffix}
            )
            if not rows:
                raise RuntimeError("Unrecognized draft branch")
            [(origin_branch, origin_sha, sync_sha)] = rows

        if (
            revert
            and sync_sha
            and self._repo.commit(origin_branch).hexsha != origin_sha
        ):
            raise RuntimeError("Parent branch has moved, please rebase first")

        if clean:
            # We delete files which have been deleted in the draft manually,
            # otherwise they would still show up as untracked.
            origin_delta = self._delta(f"{origin_branch}..{branch}")
            deleted = self._untracked() & origin_delta.deleted
            for path in deleted:
                os.remove(osp.join(self._repo.working_dir, path))
            _logger.info("Cleaned up files. [deleted=%s]", deleted)

        # We do a small dance to move back to the original branch, keeping the
        # draft branch untouched. See https://stackoverflow.com/a/15993574 for
        # the inspiration.
        self._repo.git.checkout(detach=True)
        self._repo.git.reset("-N", origin_branch)
        self._repo.git.checkout(origin_branch)

        if revert:
            # We revert the relevant files if needed. If a sync commit had been
            # created, we simply revert to it. Otherwise we compute which files
            # have changed due to draft commits and revert only those.
            if sync_sha:
                delta = self._delta(sync_sha)
                if delta.changed:
                    self._repo.git.checkout(sync_sha, "--", ".")
                _logger.info("Reverted to sync commit. [sha=%s]", sync_sha)
            else:
                origin_delta = self._delta(f"{origin_branch}..{branch}")
                head_delta = self._delta("HEAD")
                changed = head_delta.touched & origin_delta.changed
                if changed:
                    self._repo.git.checkout("--", *changed)
                deleted = head_delta.touched & origin_delta.deleted
                if deleted:
                    self._repo.git.rm("--", *deleted)
                _logger.info(
                    "Reverted touched files. [changed=%s, deleted=%s]",
                    changed,
                    deleted,
                )

        if delete:
            self._repo.git.branch("-D", branch.name)
            _logger.debug("Deleted branch %s.", branch)

        return branch.name

    def _untracked(self) -> frozenset[str]:
        text = self._repo.git.ls_files(exclude_standard=True, others=True)
        return frozenset(text.splitlines())

    def _delta(self, spec) -> _Delta:
        changed = list[str]()
        deleted = list[str]()
        for line in self._repo.git.diff(spec, name_status=True).splitlines():
            state, name = line.split(None, 1)
            if state == "D":
                deleted.append(name)
            else:
                changed.append(name)
        return _Delta(changed=frozenset(changed), deleted=frozenset(deleted))


@dataclasses.dataclass(frozen=True)
class _Delta:
    changed: frozenset[str]
    deleted: frozenset[str]

    @property
    def touched(self) -> frozenset[str]:
        return self.changed | self.deleted


class _OperationRecorder(ToolVisitor):
    def __init__(self) -> None:
        self.operations = list[_Operation]()

    def on_list_files(
        self, paths: Sequence[PurePosixPath], reason: str | None
    ) -> None:
        self._record(reason, "list_files", count=len(paths))

    def on_read_file(
        self, path: PurePosixPath, contents: str | None, reason: str | None
    ) -> None:
        self._record(
            reason,
            "read_file",
            path=str(path),
            size=-1 if contents is None else len(contents),
        )

    def on_write_file(
        self, path: PurePosixPath, contents: str, reason: str | None
    ) -> None:
        self._record(reason, "write_file", path=str(path), size=len(contents))

    def on_delete_file(self, path: PurePosixPath, reason: str | None) -> None:
        self._record(reason, "delete_file", path=str(path))

    def _record(self, reason: str | None, tool: str, **kwargs) -> None:
        op = _Operation(
            tool=tool, details=kwargs, reason=reason, start=datetime.now()
        )
        _logger.debug("Recorded operation. [op=%s]", op)
        self.operations.append(op)


@dataclasses.dataclass(frozen=True)
class _Operation:
    tool: str
    details: JSONObject
    reason: str | None
    start: datetime


def _default_title(prompt: str) -> str:
    return textwrap.shorten(prompt, break_on_hyphens=False, width=72)
