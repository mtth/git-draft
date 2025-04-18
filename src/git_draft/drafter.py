"""Git state management logic"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import dataclasses
from datetime import datetime, timedelta
import enum
import json
import logging
from pathlib import Path, PurePosixPath
import re
import textwrap
import time
from typing import Literal

from .bots import Action, Bot, Goal
from .common import JSONObject, Table, qualified_class_name
from .git import Repo
from .prompt import PromptRenderer, TemplatedPrompt
from .store import Store, sql
from .toolbox import StagingToolbox, ToolVisitor


_logger = logging.getLogger(__name__)


class Accept(enum.Enum):
    """Valid change accept mode"""

    MANUAL = 0
    CHECKOUT = enum.auto()
    FINALIZE = enum.auto()


@dataclasses.dataclass(frozen=True)
class Draft:
    """Generated changes"""

    folio: Folio
    seqno: int

    @property
    def ref(self) -> str:
        return _draft_ref(self.folio_id, self.seqno)


def _draft_ref(folio_id: int, seqno: int) -> str:
    return f"refs/drafts/{folio_id}/{seqno}"


_FOLIO_BRANCH_NAMESPACE = "drafts"

_folio_branch_pattern = re.compile(_FOLIO_BRANCH_NAMESPACE + r"/(\d+)")

FolioBranchSuffix = Literal["live", "upstream"]


@dataclasses.dataclass(frozen=True)
class Folio:
    """Collection of drafts"""

    id: int

    def branch_name(self, suffix: FolioBranchSuffix = "live") -> str:
        return f"{_FOLIO_BRANCH_NAMESPACE}/{self.id}/{suffix}"


def _active_folio(repo: Repo) -> Folio | None:
    active_branch = repo.active_branch()
    if not active_branch:
        return None
    match = _folio_branch_pattern.fullmatch(active_branch)
    if not match:
        return None
    return Folio(int(match[1]))


class Drafter:
    """Draft state orchestrator"""

    def __init__(self, store: Store, repo: Repo) -> None:
        with store.cursor() as cursor:
            cursor.executescript(sql("create-tables"))
        self._store = store
        self._repo = repo

    @classmethod
    def create(cls, store: Store, path: str | None = None) -> Drafter:
        repo = Repo.enclosing(Path(path) if path else Path.cwd())
        return cls(store, repo)

    def generate_draft(  # noqa: PLR0913
        self,
        prompt: str | TemplatedPrompt,
        bot: Bot,
        accept: Accept = Accept.MANUAL,
        bot_name: str | None = None,
        prompt_transform: Callable[[str], str] | None = None,
        reset: bool = False,
        timeout: float | None = None,
        tool_visitors: Sequence[ToolVisitor] | None = None,
    ) -> Draft:
        if timeout is not None:
            raise NotImplementedError()  # TODO: Implement

        if self._repo.has_staged_changes():
            if not reset:
                raise ValueError("Please commit or reset any staged changes")
            self._repo.git("reset")

        # Ensure that we are on a draft branch.
        folio = _active_folio(self._repo)
        if not folio:
            folio = self._create_folio()
        self._sync_folio(folio)

        # Handle prompt templating and editing.
        prompt_contents = self._prepare_prompt(prompt, prompt_transform)
        with self._store.cursor() as cursor:
            [(prompt_id, seqno)] = cursor.execute(
                sql("add-prompt"),
                {
                    "folio_id": folio.id,
                    "template": prompt.template
                    if isinstance(prompt, TemplatedPrompt)
                    else None,
                    "contents": prompt_contents,
                },
            )

        operation_recorder = _OperationRecorder()
        change = self._generate_change(
            bot,
            Goal(prompt_contents, timeout),
            [operation_recorder, *list(tool_visitors or [])],
        )
        change.add_ref(folio.id, seqno)

        with self._store.cursor() as cursor:
            cursor.execute(
                sql("add-action"),
                {
                    "commit_sha": change.commit,
                    "prompt_id": prompt_id,
                    "bot_name": bot_name,
                    "bot_class": qualified_class_name(bot.__class__),
                    "walltime_seconds": change.walltime.total_seconds(),
                    "request_count": change.action.request_count,
                    "token_count": change.action.token_count,
                },
            )
            cursor.executemany(
                sql("add-operation"),
                [
                    {
                        "commit_sha": change.commit,
                        "tool": o.tool,
                        "reason": o.reason,
                        "details": json.dumps(o.details),
                        "started_at": o.start,
                    }
                    for o in operation_recorder.operations
                ],
            )
        _logger.info("Created new change in folio %s.", folio.id)

        delta = change.delta()
        if delta and accept.value >= Accept.CHECKOUT.value:
            delta.apply()
        if accept.value >= Accept.FINALIZE.value:
            self.finalize_folio()
        return Draft(folio, seqno)

    def _prepare_prompt(
        self,
        prompt: str | TemplatedPrompt,
        prompt_transform: Callable[[str], str] | None,
    ) -> str:
        if isinstance(prompt, TemplatedPrompt):
            renderer = PromptRenderer.for_toolbox(StagingToolbox(self._repo))
            contents = renderer.render(prompt)
        else:
            contents = prompt
        if prompt_transform:
            contents = prompt_transform(contents)
        if not contents.strip():
            raise ValueError("Empty prompt")
        return contents

    def _generate_change(
        self,
        folio: Folio,
        seqno: int,
        bot: Bot,
        goal: Goal,
        tool_visitors: Sequence[ToolVisitor],
    ) -> _Change:
        # Trigger code generation.
        _logger.debug("Running bot... [bot=%s]", bot)
        toolbox = StagingToolbox(self._repo, tool_visitors)
        start_time = time.perf_counter()
        action = bot.act(goal, toolbox)
        end_time = time.perf_counter()
        walltime = end_time - start_time
        _logger.info("Completed bot action. [action=%s]", action)

        # Generate an appropriate commit.
        title = action.title
        if not title:
            title = _default_title(goal.prompt)
        commit_sha = self._repo.git(
            "commit",
            "--allow-empty",
            "--no-verify",
            "-m",
            f"draft! {title}\n\n{goal.prompt}",
        ).stdout

        # Reference the commit so that it doesn't get GC'ed, and update the
        # folio's upstream branch to enable easier diffing.
        self._repo.git(
            "update-ref",
            _draft_ref(folio.id, seqno),
            commit_sha,
        )
        self._repo.git(
            "update-ref",
            f"refs/heads/{folio.branch_name('upstream')}",
            commit_sha,
        )

        return _Change(
            commit_sha,
            timedelta(seconds=walltime),
            action,
        )

    def finalize_folio(self) -> Folio:
        folio = _active_folio(self._repo)
        if not folio:
            raise RuntimeError("Not currently on a draft branch")
        self._sync_folio(folio)

        with self._store.cursor() as cursor:
            rows = cursor.execute(sql("get-folio-by-id"), {"id": folio.id})
            if not rows:
                raise RuntimeError("Unrecognized draft branch")
            [(origin_branch, origin_sha)] = rows

        # We do a small dance to move back to the original branch. See
        # https://stackoverflow.com/a/15993574 for the inspiration.
        self._repo.git("checkout", "--detach")
        self._repo.git("reset", "-N", origin_branch)
        self._repo.git("checkout", origin_branch)
        self._repo.git(
            "branch",
            "-D",
            folio.branch_name(),
            folio.branch_name("upstream"),
        )

        _logger.info("Exited %s.", folio)
        return folio

    def _create_folio(self) -> Folio:
        origin_branch = self._repo.active_branch()
        if origin_branch is None:
            raise RuntimeError("No currently active branch")
        origin_sha = self.git("rev-parse", "HEAD").stdout

        with self._store.cursor() as cursor:
            [(folio_id,)] = cursor.execute(
                sql("add-folio"),
                {
                    "repo_uuid": str(self._repo.uuid),
                    "origin_branch": origin_branch,
                    "origin_sha": origin_sha,
                },
            )
        folio = Folio(folio_id)

        self._repo.git("checkout", "--detach")
        upstream_branch = folio.branch_name("upstream")
        self._repo.git("branch", upstream_branch)
        live_branch = folio.branch_name()
        self._repo.git("branch", "--track", live_branch, upstream_branch)
        self._repo.git("checkout", live_branch)
        return folio

    def _sync_folio(self, folio: Folio) -> None:
        raise NotImplementedError()  # TODO: Implement

    def history_table(self, folio_id: int | None = None) -> Table:
        repo_uuid = self._repo.uuid
        folio = Folio(folio_id) if folio_id else _active_folio(self._repo)
        with self._store.cursor() as cursor:
            if folio:
                results = cursor.execute(
                    sql("list-folio-prompts"),
                    {
                        "repo_uuid": str(repo_uuid),
                        "folio_id": folio.id,
                    },
                )
            else:
                results = cursor.execute(
                    sql("list-folios"), {"repo_uuid": str(repo_uuid)}
                )
            return Table.from_cursor(results)

    def latest_draft_prompt(self) -> str | None:
        """Returns the latest prompt for the current draft"""
        folio = _active_folio(self._repo)
        if not folio:
            return None
        with self._store.cursor() as cursor:
            result = cursor.execute(
                sql("get-latest-folio-prompt"),
                {
                    "repo_uuid": str(self._repo.uuid),
                    "folio_id": folio.id,
                },
            ).fetchone()
            return result[0] if result else None


@dataclasses.dataclass(frozen=True)
class _Change:
    """A bot-generated draft, may be a no-op"""

    commit_sha: str
    walltime: timedelta
    action: Action


class ConflictError(Exception):
    """A change could not be applied cleanly"""


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

    def on_rename_file(
        self,
        src_path: PurePosixPath,
        dst_path: PurePosixPath,
        reason: str | None,
    ) -> None:
        self._record(
            reason,
            "rename_file",
            src_path=str(src_path),
            dst_path=str(dst_path),
        )

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
