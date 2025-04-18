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
from re import Match
import textwrap
import time

from .bots import Action, Bot, Goal
from .common import JSONObject, Table, qualified_class_name
from .git import Commit, Repo
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

    folio_id: int
    seqno: int

    @property
    def branch(self) -> str:
        return _Branch(self.folio_id).name

    @property
    def ref(self) -> str:
        return _draft_ref(self.folio_id, self.seqno)


def _draft_ref(folio_id: int, seqno: int) -> str:
    return f"refs/drafts/{folio_id}/{seqno}"


@dataclasses.dataclass(frozen=True)
class Folio:
    """Collection of drafts"""

    id: int


@dataclasses.dataclass(frozen=True)
class _Branch:
    """Draft folio branch"""

    _PREFIX = "drafts/"
    _pattern = re.compile(_PREFIX + r"(\d+)")

    folio_id: int

    @property
    def name(self) -> str:
        return f"{self._PREFIX}{self.folio_id}"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def active(cls, repo: Repo, name: str | None = None) -> _Branch | None:
        match: Match | None = None
        active_branch = name or repo.active_branch()
        if active_branch:
            match = cls._pattern.fullmatch(active_branch)
        if not match:
            if name:
                raise ValueError(f"Not a valid draft branch: {name!r}")
            return None
        return _Branch(int(match[1]))


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
        branch = _Branch.active(self._repo)
        if branch:
            self._stage_changes()
            _logger.debug("Reusing active branch %s.", branch)
        else:
            branch = self._create_branch()
            _logger.debug("Created branch %s.", branch)

        # Handle prompt templating and editing.
        prompt_contents = self._prepare_prompt(prompt, prompt_transform)
        with self._store.cursor() as cursor:
            [(prompt_id, seqno)] = cursor.execute(
                sql("add-prompt"),
                {
                    "folio_id": branch.folio_id,
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
        change.add_ref(branch.folio_id, seqno)

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
        _logger.info("Created new change on %s.", branch)

        delta = change.delta()
        if delta and accept.value >= Accept.CHECKOUT.value:
            delta.apply()
        if accept.value >= Accept.FINALIZE.value:
            self.finalize_folio()
        return Draft(branch.folio_id, seqno)

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
        toolbox.trim_index()
        title = action.title
        if not title:
            title = _default_title(goal.prompt)
        commit = self._repo.create_commit(
            f"draft! {title}\n\n{goal.prompt}",
            skip_hooks=True,
        )

        return _Change(
            commit.sha, timedelta(seconds=walltime), action, self._repo
        )

    def finalize_folio(self) -> Folio:
        branch = _Branch.active(self._repo)
        if not branch:
            raise RuntimeError("Not currently on a draft branch")
        self._stage_changes()

        with self._store.cursor() as cursor:
            rows = cursor.execute(
                sql("get-folio-by-id"), {"id": branch.folio_id}
            )
            if not rows:
                raise RuntimeError("Unrecognized draft branch")
            [(origin_branch, origin_sha)] = rows

        # We do a small dance to move back to the original branch, keeping the
        # draft branch untouched. See https://stackoverflow.com/a/15993574 for
        # the inspiration.
        self._repo.git("checkout", "--detach")
        self._repo.git("reset", "-N", origin_branch)
        self._repo.git("checkout", origin_branch)
        self._repo.git("branch", "-D", branch.name)

        _logger.info("Exited %s.", branch)
        return Folio(branch.folio_id)

    def _create_branch(self) -> _Branch:
        if self._repo.active_branch() is None:
            raise RuntimeError("No currently active branch")
        origin_branch = self._repo.active_branch()
        origin_sha = self._repo.head_commit().sha

        with self._store.cursor() as cursor:
            [(folio_id,)] = cursor.execute(
                sql("add-folio"),
                {
                    "repo_uuid": str(self._repo.uuid),
                    "origin_branch": origin_branch,
                    "origin_sha": origin_sha,
                },
            )

        self._repo.git("checkout", "--detach")
        self._stage_changes()
        branch = _Branch(folio_id)
        self._repo.checkout_new_branch(branch.name)
        return branch

    def _stage_changes(self) -> Commit | None:
        self._repo.git("add", "--all")
        if not self._repo.has_staged_changes():
            return None
        return self._repo.create_commit("draft! sync")

    def history_table(self, branch_name: str | None = None) -> Table:
        repo_uuid = self._repo.uuid
        branch = _Branch.active(self._repo, branch_name)
        with self._store.cursor() as cursor:
            if branch:
                results = cursor.execute(
                    sql("list-folio-prompts"),
                    {
                        "repo_uuid": str(repo_uuid),
                        "folio_id": branch.folio_id,
                    },
                )
            else:
                results = cursor.execute(
                    sql("list-folios"), {"repo_uuid": str(repo_uuid)}
                )
            return Table.from_cursor(results)

    def latest_draft_prompt(self) -> str | None:
        """Returns the latest prompt for the current draft"""
        branch = _Branch.active(self._repo)
        if not branch:
            return None
        with self._store.cursor() as cursor:
            result = cursor.execute(
                sql("get-latest-folio-prompt"),
                {
                    "repo_uuid": str(self._repo.uuid),
                    "folio_id": branch.folio_id,
                },
            ).fetchone()
            return result[0] if result else None


type _CommitSHA = str


@dataclasses.dataclass(frozen=True)
class _Change:
    """A bot-generated draft, may be a no-op"""

    commit: _CommitSHA
    walltime: timedelta
    action: Action
    repo: Repo = dataclasses.field(repr=False)

    def add_ref(self, folio_id: int, seqno: int) -> None:
        self.repo.git(
            "update-ref",
            _draft_ref(folio_id, seqno),
            self.commit,
        )

    def delta(self) -> _Delta | None:
        diff = self.repo.git("diff-tree", "--patch", self.commit).stdout
        return _Delta(diff, self.repo) if diff else None


@dataclasses.dataclass(frozen=True)
class _Delta:
    """A change's effects, guaranteed non-empty"""

    diff: str
    repo: Repo = dataclasses.field(repr=False)

    def apply(self) -> None:
        # For patch applcation to work as expected (adding conflict markers as
        # needed), files in the patch must exist in the index.
        self.repo.git("add", "--all")
        call = self.repo.git(
            "apply", "--3way", "-", stdin=self.diff, expect_codes=()
        )
        if "with conflicts" in call.stderr:
            raise ConflictError()
        if call.code != 0:
            raise NotImplementedError()  # TODO: Raise better error
        self.repo.git("reset")


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
