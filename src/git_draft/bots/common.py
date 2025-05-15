"""Shared bot utilities"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from ..common import ensure_state_home, qualified_class_name
from ..toolbox import Toolbox


@dataclasses.dataclass(frozen=True)
class Goal:
    """Bot request"""

    prompt: str
    # TODO: Add timeout.


@dataclasses.dataclass
class Action:
    """End-of-action statistics

    This dataclass is not frozen to allow bot implementors to populate its
    fields incrementally.
    """

    title: str | None = None
    request_count: int | None = None
    token_count: int | None = None
    question: str | None = None

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

    async def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        """Runs the bot, striving to achieve the goal with the given toolbox"""
        raise NotImplementedError()
