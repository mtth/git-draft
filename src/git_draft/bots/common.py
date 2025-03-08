from __future__ import annotations

import dataclasses
from pathlib import Path

from ..common import ensure_state_home, qualified_class_name
from ..toolbox import Toolbox


@dataclasses.dataclass(frozen=True)
class Goal:
    prompt: str
    timeout: float | None


@dataclasses.dataclass(frozen=True)
class Action:
    title: str | None = None


class Bot:
    @classmethod
    def state_folder_path(cls, ensure_exists=False) -> Path:
        name = qualified_class_name(cls)
        path = ensure_state_home() / "bots" / name
        if ensure_exists:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        raise NotImplementedError()
