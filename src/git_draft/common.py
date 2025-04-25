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
from typing import Any, ClassVar, Self

import prettytable
import xdg_base_dirs
import yaspin
import yaspin.core


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

    def spinner(
        self, text: str
    ) -> contextlib.AbstractContextManager[FeedbackSpinner]:
        raise NotImplementedError()

    @staticmethod
    def dynamic() -> Feedback:
        return _DynamicFeedback()

    @staticmethod
    def static() -> Feedback:
        return _StaticFeedback()


class FeedbackSpinner:
    """Operation feedback tracker"""

    def update(self, text: str, **kwargs) -> None: ...
    def report(self, text: str) -> None: ...


class _DynamicFeedback(Feedback):
    @contextlib.contextmanager
    def spinner(self, text: str) -> Iterator[FeedbackSpinner]:
        with yaspin.yaspin(text=text) as spinner:
            try:
                yield _DynamicFeedbackSpinner(spinner)
            except Exception:
                spinner.fail("✗")
                raise
            else:
                spinner.ok("✓")


def _tagged(text: str, /, **kwargs) -> str:
    tags = [
        f"{key}={val}"
        for key, val in kwargs.items()
        if val is not None
    ]
    return f"{text} [{', '.join(tags)}]" if tags else text


class _DynamicFeedbackSpinner(FeedbackSpinner):
    def __init__(self, yaspin: yaspin.core.Yaspin) -> None:
        self._yaspin = yaspin

    def update(self, text: str, **kwargs) -> None:
        self._yaspin.text = _tagged(text, **kwargs)

    def report(self, text: str) -> None:
        self._yaspin.write(f"☞ {text}")


class _StaticFeedback(Feedback):
    @contextlib.contextmanager
    def spinner(self, text: str) -> Iterator[FeedbackSpinner]:
        yield _StaticFeedbackSpinner.start(text)


class _StaticFeedbackSpinner(FeedbackSpinner):
    @classmethod
    def start(cls, text: str) -> Self:
        spinner = cls()
        spinner._print(text)
        return spinner

    def _print(self, message: str, **kwargs) -> None:
        print(_tagged(message, spinner=id(self), **kwargs))  # noqa

    def update(self, text: str, **kwargs) -> None:
        self._print(text, **kwargs)

    def report(self, text: str) -> None:
        self._print(text)
