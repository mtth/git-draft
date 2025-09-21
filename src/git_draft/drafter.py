"""Git state management logic"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
import dataclasses
from datetime import datetime, timedelta
import logging
import re
import textwrap
import time
from typing import Literal

from .bots import ActionSummary, Bot, Goal
from .common import (
    UnreachableError,
    now,
    qualified_class_name,
    reindent,
    tagged,
)
from .events import (
    Event,
    EventConsumer,
    event_decoders,
    event_encoder,
    feedback_events,
    worktree_events,
)
from .git import SHA, Repo
from .progress import Progress, ProgressFeedback
from .prompt import TemplatedPrompt
from .store import Store, sql
from .worktrees import GitWorktree


_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Draft:
    """Generated changes"""

    folio: Folio
    seqno: int
    is_noop: bool
    has_pending_question: bool
    walltime: timedelta
    token_count: int | None

    @property
    def ref(self) -> str:
        return _draft_ref(self.folio.id, self.seqno)


_DRAFT_REF_PREFIX = "refs/drafts/"


def _draft_ref(folio_id: int, suffix: int | str) -> str:
    return f"{_DRAFT_REF_PREFIX}{folio_id}/{suffix}"


def _parse_draft_ref(ref: str) -> tuple[int, int | None]:
    ref = ref.removeprefix(_DRAFT_REF_PREFIX)
    parts = ref.split("/")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else None


_FOLIO_BRANCH_NAMESPACE = "draft"

_FOLIO_UPSTREAM_BRANCH_SUFFIX = "+"

_folio_branch_pattern = re.compile(_FOLIO_BRANCH_NAMESPACE + r"/(\d+)")


@dataclasses.dataclass(frozen=True)
class Folio:
    """Collection of drafts"""

    id: int

    def branch_name(self) -> str:
        return f"{_FOLIO_BRANCH_NAMESPACE}/{self.id}"

    def upstream_branch_name(self) -> str:
        return self.branch_name() + _FOLIO_UPSTREAM_BRANCH_SUFFIX


def _maybe_active_folio(repo: Repo) -> Folio | None:
    active_branch = repo.active_branch()
    if not active_branch:
        return None
    match = _folio_branch_pattern.fullmatch(active_branch)
    if not match:
        return None
    return Folio(int(match[1]))


def _active_folio(repo: Repo) -> Folio:
    folio = _maybe_active_folio(repo)
    if not folio:
        raise RuntimeError("Not currently on a draft branch")
    return folio


#: Select ort strategies.
DraftMergeStrategy = Literal[
    "ours",
    "theirs",
    "ignore-space-change",
    "ignore-all-space",
    "ignore-space-at-eol",
    "ignore-cr-at-eol",
    "find-renames",
]


class Drafter:
    """Draft state orchestrator"""

    def __init__(self, store: Store, repo: Repo, progress: Progress) -> None:
        self._store = store
        self._repo = repo
        self._progress = progress

    @classmethod
    def create(cls, repo: Repo, store: Store, progress: Progress) -> Drafter:
        with store.cursor() as cursor:
            cursor.executescript(sql("create-tables"))
        return cls(store, repo, progress)

    async def generate_draft(
        self,
        prompt: str | TemplatedPrompt,
        bot: Bot,
        merge_strategy: DraftMergeStrategy | None = None,
        prompt_transform: Callable[[str], str] | None = None,
    ) -> Draft:
        with self._progress.spinner("Preparing prompt...") as spinner:
            # Handle prompt templating and editing. We do this first in case
            # this fails, to avoid creating unnecessary branches.
            tree, dirty = GitWorktree.for_working_dir(self._repo)
            with spinner.hidden():
                prompt_contents = self._prepare_prompt(
                    prompt,
                    prompt_transform,
                    tree,
                )
            template_name = (
                prompt.name if isinstance(prompt, TemplatedPrompt) else None
            )
            spinner.update(
                "Prepared prompt.",
                template=template_name,
                length=len(prompt_contents),
            )

        # Ensure that we are in a folio.
        folio = _maybe_active_folio(self._repo)
        if folio:
            self._progress.report(
                "Reusing active draft branch.", name=folio.branch_name()
            )
        else:
            folio = self._create_folio()
        with self._store.cursor() as cursor:
            [(prompt_id, seqno)] = cursor.execute(
                sql("add-prompt"),
                {
                    "folio_id": folio.id,
                    "template": template_name,
                    "contents": prompt_contents,
                },
            )

        # Run the bot to generate the change.
        event_recorder = _EventRecorder(self._progress)
        with self._progress.spinner("Running bot...") as spinner:
            feedback = spinner.feedback(event_recorder)
            change = await self._generate_change(
                bot,
                Goal(prompt_contents),
                tree.with_event_consumer(event_recorder),
                feedback,
            )
            spinner.update(
                "Completed bot run.",
                runtime=round(change.walltime.total_seconds(), 1),
                tokens=change.action.token_count,
                turns=change.action.turn_count,
                cost=change.action.cost,
            )

        # Create git commits, references, and update branches.
        draft = Draft(
            folio=folio,
            seqno=seqno,
            is_noop=change.is_noop,
            has_pending_question=feedback.pending_question is not None,
            walltime=change.walltime,
            token_count=change.action.token_count,
        )
        with self._progress.spinner("Creating draft commit...") as spinner:
            if dirty:
                parent_commit_rev = self._commit_tree(
                    tree.sha(), "HEAD", "sync(act)"
                )
                _logger.info(
                    "Created sync commit. [sha=%s]", parent_commit_rev
                )
            else:
                parent_commit_rev = "HEAD"
                _logger.info("Skipping sync commit, tree is clean.")
            commit_sha = self._record_change(
                change, parent_commit_rev, folio, seqno
            )
            # TODO: Trim commits (sync and prompt of files which have not been
            # operated on). This will improve the UX by allowing fast-forward
            # when other files are edited.
            with self._store.cursor() as cursor:
                cursor.execute(
                    sql("add-action-summary"),
                    {
                        "prompt_id": prompt_id,
                        "bot_class": qualified_class_name(bot.__class__),
                        "walltime_seconds": change.walltime.total_seconds(),
                        "turn_count": change.action.turn_count,
                        "token_count": change.action.token_count,
                        "pending_question": feedback.pending_question,
                    },
                )
                encoder = event_encoder()
                cursor.executemany(
                    sql("add-action-event"),
                    [
                        {
                            "prompt_id": prompt_id,
                            "occurred_at": dt,
                            "class": e.__class__.__name__,
                            "data": encoder.encode(e),
                        }
                        for (dt, e) in event_recorder.events()
                    ],
                )
                spinner.update("Created draft commit.", ref=draft.ref)

        _logger.info("Created new draft in folio %s.", folio.id)

        if merge_strategy:
            with self._progress.spinner("Merging changes...") as spinner:
                if parent_commit_rev != "HEAD":
                    # If there was a sync(prompt) commit, we move forward to
                    # it. This will avoid conflicts with earlier changes.
                    self._repo.git("reset", "--soft", parent_commit_rev)
                self._sync_head("merge")
                self._repo.git(
                    "merge",
                    "--no-ff",
                    "-X",
                    merge_strategy,
                    "-m",
                    "draft! merge",
                    commit_sha,
                )
                self._repo.git(
                    "update-ref",
                    f"refs/heads/{folio.upstream_branch_name()}",
                    "HEAD",
                )
                spinner.update("Merged changes.")

        return draft

    def quit_folio(self) -> None:
        folio = _active_folio(self._repo)
        with self._store.cursor() as cursor:
            rows = cursor.execute(sql("get-folio-by-id"), {"id": folio.id})
            if not rows:
                raise RuntimeError("Unrecognized draft branch")
            [(origin_branch,)] = rows

        # Check that the origin branch has not moved to avoid unexpected diffs.
        check_call = self._repo.git(
            "merge-base",
            "--is-ancestor",
            origin_branch,
            "HEAD",
            expect_codes=(),
        )
        if check_call.code:
            raise RuntimeError("Origin branch diverged, please rebase first")

        with self._progress.spinner("Switching branch...") as spinner:
            # Create a reference to the current state for later analysis.
            self._sync_head("finalize")
            self._repo.git("update-ref", _draft_ref(folio.id, "@"), "HEAD")

            # Move back to the original branch, doing a little dance to keep
            # the state. See https://stackoverflow.com/a/15993574 for the
            # inspiration.
            self._repo.git("checkout", "--detach")
            self._repo.git("reset", "--soft", origin_branch)
            self._repo.git("checkout", origin_branch)

            # Clean up folio branches.
            self._repo.git(
                "branch",
                "-D",
                folio.branch_name(),
                folio.upstream_branch_name(),
            )
            spinner.update(
                "Switched back to origin branch.",
                name=origin_branch,
            )

        _logger.info("Quit %s.", folio)

    def _create_folio(self) -> Folio:
        with self._progress.spinner("Creating draft branch...") as spinner:
            origin_branch = self._repo.active_branch()
            if origin_branch is None:
                raise RuntimeError("No currently active branch")

            with self._store.cursor() as cursor:
                [(folio_id,)] = cursor.execute(
                    sql("add-folio"),
                    {
                        "repo_uuid": str(self._repo.uuid),
                        "origin_branch": origin_branch,
                    },
                )
            folio = Folio(folio_id)

            self._repo.git("checkout", "--detach")
            upstream_branch = folio.upstream_branch_name()
            self._repo.git("branch", upstream_branch)
            live_branch = folio.branch_name()
            self._repo.git("branch", "--track", live_branch, upstream_branch)
            self._repo.git("checkout", live_branch)

            spinner.update("Switched to new draft branch.", name=live_branch)
        return folio

    def _sync_head(self, scope: str) -> None:
        self._repo.git("add", "-A")
        index_call = self._repo.git(
            "diff-index",
            "--quiet",
            "--cached",
            "HEAD",
            expect_codes=(),
        )
        if index_call.code:
            self._repo.git(
                "commit", "--no-verify", "-m", f"draft! sync({scope})"
            )

    def _prepare_prompt(
        self,
        prompt: str | TemplatedPrompt,
        prompt_transform: Callable[[str], str] | None,
        tree: GitWorktree,
    ) -> str:
        if isinstance(prompt, TemplatedPrompt):
            contents = prompt.render(tree)
        else:
            contents = prompt
        if prompt_transform:
            contents = prompt_transform(contents)
        if not contents.strip():
            raise ValueError("Missing or empty prompt")
        return contents

    async def _generate_change(
        self,
        bot: Bot,
        goal: Goal,
        tree: GitWorktree,
        feedback: ProgressFeedback,
    ) -> _Change:
        old_tree_sha = tree.sha()

        start_time = time.perf_counter()
        _logger.debug("Running bot... [bot=%s]", bot)
        action = await bot.act(goal, tree, feedback)
        _logger.info("Completed bot action. [action=%s]", action)
        end_time = time.perf_counter()

        walltime = end_time - start_time
        message = (
            reindent(action.message, width=72)
            if action.message
            else _default_message(goal.prompt)
        )
        new_tree_sha = tree.sha()
        return _Change(
            walltime=timedelta(seconds=walltime),
            action=action,
            commit_message=f"act: {message}",
            tree_sha=new_tree_sha,
            is_noop=new_tree_sha == old_tree_sha,
        )

    def _record_change(
        self, change: _Change, parent_commit_rev: str, folio: Folio, seqno: int
    ) -> SHA:
        commit_sha = self._commit_tree(
            change.tree_sha, parent_commit_rev, change.commit_message
        )
        _logger.debug("Created prompt commit. [sha=%r]", commit_sha)
        self._repo.git(
            "update-ref",
            f"refs/heads/{folio.upstream_branch_name()}",
            commit_sha,
        )
        # We also add a reference to the commit so that it doesn't get GC'ed
        # when the upstream branch moves. This also makes it easy to visualize
        # the change using `git diff refs/drafts/xx/yy`.
        self._repo.git("update-ref", _draft_ref(folio.id, seqno), commit_sha)
        return commit_sha

    def _commit_tree(
        self, tree_sha: SHA, parent_rev: str, message: str
    ) -> SHA:
        return self._repo.git(
            "commit-tree",
            "-p",
            parent_rev,
            "-m",
            f"draft! {message}",
            tree_sha,
        ).stdout

    def latest_draft_prompt(self) -> str | None:
        """Returns the latest prompt for the current draft"""
        folio = _maybe_active_folio(self._repo)
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
            if not result:
                return None
            prompt, question = result
        if question:
            prompt = "\n\n".join([prompt, reindent(question, prefix="> ")])
        return prompt

    def list_draft_events(
        self, draft_ref: str | None = None
    ) -> Iterator[DraftEventProperties]:
        if draft_ref:
            folio_id, seqno = _parse_draft_ref(draft_ref)
        else:
            folio = _active_folio(self._repo)
            folio_id = folio.id
            seqno = None
        with self._store.cursor() as cursor:
            rows = cursor.execute(
                sql("list-action-events"),
                {"folio_id": folio_id, "seqno": seqno},
            )
            decoders = event_decoders()
            for row in rows:
                occurred_at, class_name, data = row
                event = decoders[class_name].decode(data)
                description = _format_event(event)
                yield DraftEventProperties(
                    occurred_at, class_name, description
                )


@dataclasses.dataclass(frozen=True)
class DraftEventProperties:
    """Formattable properties corresponding to a draft's event"""

    occurred_at: str
    class_name: str
    description: str


@dataclasses.dataclass(frozen=True)
class _Change:
    """A bot-generated draft, may be a no-op"""

    action: ActionSummary
    walltime: timedelta
    commit_message: str
    tree_sha: SHA
    is_noop: bool


class _EventRecorder(EventConsumer):
    """Visitor which keeps track of which operations have been performed

    This is useful to store a summary of each change in our database for later
    analysis.
    """

    def __init__(self, progress: Progress) -> None:
        self._events = list[tuple[datetime, Event]]()
        self._progress = progress

    def events(self) -> Sequence[tuple[datetime, Event]]:
        return sorted(list(self._events))

    def on_event(self, event: Event) -> None:
        self._events.append((now(), event))
        if formatted := _format_internal_event(event):
            self._progress.report(formatted)


def _format_internal_event(event: Event) -> str:
    match event:
        case worktree_events.ListFiles(path_count):
            return f"Listed {path_count} files."
        case worktree_events.ReadFile(path, char_count):
            return tagged(f"Read {path}.", length=char_count)
        case worktree_events.WriteFile(path, char_count):
            return tagged(f"Wrote {path}.", length=char_count)
        case worktree_events.DeleteFile(path):
            return f"Deleted {path}."
        case worktree_events.RenameFile(src_path, dst_path):
            return f"Renamed {src_path} to {dst_path}."
        case worktree_events.StartEditingFiles():
            return "Started editing files..."
        case worktree_events.StopEditingFiles():
            return "Stopped editing files."
        case _:
            return ""


def _format_event(event: Event) -> str:
    if formatted := _format_internal_event(event):
        return formatted
    match event:
        case feedback_events.NotifyUser(update):
            return update
        case feedback_events.RequestUserGuidance(question):
            return question
        case feedback_events.ReceiveUserGuidance(answer):
            return answer
        case _:
            raise UnreachableError()


def _default_message(prompt: str) -> str:
    return textwrap.shorten(prompt, break_on_hyphens=False, width=55)
