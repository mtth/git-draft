"""Miscellaneous utilities"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import contextlib
import dataclasses
import itertools
import logging
import os
from pathlib import Path
import sqlite3
import textwrap
import tomllib
from typing import Any, ClassVar, Protocol, Self

import prettytable
import xdg_base_dirs
import yaspin


_logger = logging.getLogger(__name__)


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

    bots: Sequence[BotConfig] = dataclasses.field(default_factory=lambda: [])
    log_level: int = logging.INFO

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


def config_string(arg: str) -> str:
    """Dereferences environment value if the input starts with `$`"""
    return os.environ[arg[1:]] if arg and arg.startswith("$") else arg


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


class Feedback:
    """User feedback interface"""

    def spinner(self, text: str) -> Iterator[FeedbackSpinner]:
        raise NotImplementedError()

    @staticmethod
    def live() -> Feedback:
        return _LiveFeedback()

    @staticmethod
    def logging() -> Feedback:
        return _LoggingFeedback()



class FeedbackSpinner(Protocol):
    """Operation feedback tracker"""

    def ok(self, text: str) -> None: ...
    def fail(self, text: str) -> None: ...



class _LiveFeedback(Feedback):
    def spinner(self, text: str) -> Iterator[FeedbackSpinner]:
        return yaspin.yaspin(text=text)


class _LoggingFeedback(Feedback):
    @contextlib.contextmanager
    def spinner(self, text: str) -> Iterator[FeedbackSpinner]:
        yield _LoggingFeedbackSpinner.start(text)


class _LoggingFeedbackSpinner:
    @classmethod
    def start(cls, text: str) -> Self:
        spinner = cls()
        spinner._log("Spinner started.", text)
        return spinner

    def _log(self, message: str, text: str) -> None:
        self._log("%s [id=%s, text=%s]", message, id(self), text)

    def ok(self, text: str) -> None:
        self._log("Spinner succeeded.", text)

    def fail(self, text: str) -> None:
        self._log("Spinner failed.", text)
