"""Miscellaneous utilities"""

from __future__ import annotations

import dataclasses
import itertools
import logging
from pathlib import Path
import random
import string
import textwrap
import tomllib
from typing import Any, Mapping, Self, Sequence

import xdg_base_dirs


PROGRAM = "git-draft"


type JSONValue = Any
type JSONObject = Mapping[str, JSONValue]


package_root = Path(__file__).parent


def ensure_state_home() -> Path:
    path = xdg_base_dirs.xdg_state_home() / PROGRAM
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclasses.dataclass(frozen=True)
class Config:
    log_level: int
    bots: Sequence[BotConfig]

    @staticmethod
    def folder_path() -> Path:
        return xdg_base_dirs.xdg_config_home() / PROGRAM

    @classmethod
    def default(cls) -> Self:
        return cls(logging.INFO, [])

    @classmethod
    def load(cls) -> Self:
        path = cls.folder_path() / "config.toml"
        try:
            with open(path, "rb") as reader:
                data = tomllib.load(reader)
        except FileNotFoundError:
            return cls.default()
        else:
            return cls(
                log_level=logging.getLevelName(data["log_level"]),
                bots=[BotConfig(**v) for v in data.get("bots", [])],
            )


@dataclasses.dataclass(frozen=True)
class BotConfig:
    factory: str
    name: str | None = None
    config: JSONObject | None = None
    pythonpath: str | None = None


_random = random.Random()
_alphabet = string.ascii_lowercase + string.digits


def random_id(n: int) -> str:
    """Generates a random length n string of lowercase letters and digits"""
    return "".join(_random.choices(_alphabet, k=n))


class UnreachableError(RuntimeError):
    """Indicates unreachable code was unexpectedly executed"""


def reindent(s: str, width=0) -> str:
    """Reindents text by dedenting and optionally wrapping paragraphs"""
    paragraphs = (
        " ".join(textwrap.dedent("\n".join(g)).splitlines())
        for b, g in itertools.groupby(s.splitlines(), bool)
        if b
    )
    return "\n\n".join(
        textwrap.fill(p, width=width) if width else p for p in paragraphs
    )
