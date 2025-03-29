"""Miscellaneous utilities"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
import itertools
import logging
from pathlib import Path
import random
import sqlite3
import string
import textwrap
import tomllib
from typing import Any, ClassVar, Self

import prettytable
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
    """Overall CLI configuration"""

    log_level: int = logging.INFO
    auto_reset: bool = True
    bots: Sequence[BotConfig] = dataclasses.field(default_factory=lambda: [])

    @staticmethod
    def folder_path() -> Path:
        return xdg_base_dirs.xdg_config_home() / PROGRAM

    @classmethod
    def load(cls) -> Self:
        path = cls.folder_path() / "config.toml"
        try:
            with open(path, "rb") as reader:
                data = tomllib.load(reader)
        except FileNotFoundError:
            return cls()
        else:
            if level := data["log_level"]:
                data["log_level"] = logging.getLevelName(level)
            if bots := data["bots"]:
                data["bots"] = [BotConfig(**v) for v in bots]
            return cls(**data)


@dataclasses.dataclass(frozen=True)
class BotConfig:
    """Individual bot configuration for CLI use"""

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


def reindent(s: str, width: int = 0) -> str:
    """Reindents text by dedenting and optionally wrapping paragraphs"""
    paragraphs = (
        " ".join(textwrap.dedent("\n".join(g)).splitlines())
        for b, g in itertools.groupby(s.splitlines(), bool)
        if b
    )
    return "\n\n".join(
        textwrap.fill(p, width=width) if width else p for p in paragraphs
    )


def qualified_class_name(cls: type) -> str:
    name = cls.__qualname__
    return f"{cls.__module__}.{name}" if cls.__module__ else name


class Table:
    """Pretty-printable table"""

    _kwargs: ClassVar[Mapping[str, Any]] = dict(border=False)  # Shared options

    def __init__(self, data: prettytable.PrettyTable) -> None:
        self.data = data
        self.data.align = "l"

    def __bool__(self) -> bool:
        return len(self.data.rows) > 0

    def __str__(self) -> str:
        return str(self.data) if self else ""

    def to_json(self) -> str:
        return self.data.get_json_string(header=False)

    @classmethod
    def empty(cls) -> Self:
        return cls(prettytable.PrettyTable([], **cls._kwargs))

    @classmethod
    def from_cursor(cls, cursor: sqlite3.Cursor) -> Self:
        table = prettytable.from_db_cursor(cursor, **cls._kwargs)
        assert table
        return cls(table)
