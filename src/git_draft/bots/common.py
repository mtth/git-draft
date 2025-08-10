"""Shared bot utilities"""

from __future__ import annotations

from collections.abc import Sequence
import contextlib
import dataclasses
from pathlib import Path, PurePosixPath
from typing import Protocol

from ..common import ensure_state_home, qualified_class_name


@dataclasses.dataclass(frozen=True)
class Goal:
    """Bot request"""

    prompt: str
    # TODO: Add timeout.


class Worktree(Protocol):
    """File operations

    Implementations may not be thread-safe. Concurrent operations should be
    serialized by the caller.
    """

    def list_files(self) -> Sequence[PurePosixPath]:
        """List all files"""

    def read_file(self, path: PurePosixPath) -> str | None:
        """Get a file's contents"""

    def write_file(self, path: PurePosixPath, contents: str) -> None:
        """Update a file's contents"""

    def delete_file(self, path: PurePosixPath) -> None:
        """Remove a file"""

    def rename_file(
        self, src_path: PurePosixPath, dst_path: PurePosixPath
    ) -> None:
        """Move a file"""

    def edit_files(self) -> contextlib.AbstractContextManager[Path]:
        """Return path to a temporary folder with editable copies of all files

        Any updates are synced back to the work tree when the context exits.
        Other operations should not be performed concurrently as they may be
        stale or lost.
        """


class UserFeedback(Protocol):
    """User interactions"""

    def notify(self, update: str) -> None:
        """Report progress to the user"""

    def ask(self, question: str) -> str:
        """Request additional information from the user"""


@dataclasses.dataclass
class Action:
    """End-of-action statistics

    This dataclass is not frozen to allow bot implementors to populate its
    fields incrementally.
    """

    title: str | None = None
    request_count: int | None = None
    token_count: int | None = None

    def increment_request_count(self, n: int = 1, init: bool = False) -> None:
        self._increment("request_count", n, init)

    def increment_token_count(self, n: int, init: bool = False) -> None:
        self._increment("token_count", n, init)

    def _increment(self, attr: str, count: int, init: bool) -> None:
        if (value := getattr(self, attr)) is None:
            if not init:
                raise ValueError(f"Uninitialized action {attr}")
            setattr(self, attr, count)
        else:
            setattr(self, attr, value + count)


class Bot:
    """Code assistant bot"""

    @classmethod
    def state_folder_path(cls, ensure_exists: bool = False) -> Path:
        """Returns a path unique to this bot class

        The path can be used to store data specific to this bot implementation.
        For example a bot interacting with a stateful API may wish to store IDs
        between runs, and use this folder to do so.

        Args:
            ensure_exists: Create the folder if it does not exist.

        """
        name = qualified_class_name(cls)
        path = ensure_state_home() / "bots" / name
        if ensure_exists:
            path.mkdir(parents=True, exist_ok=True)
        return path

    async def act(
        self, goal: Goal, tree: Worktree, feedback: UserFeedback
    ) -> Action:
        """Runs the bot, striving to achieve the goal"""
        raise NotImplementedError()
