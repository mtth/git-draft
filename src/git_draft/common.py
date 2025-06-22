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


def reindent(s: str, prefix: str = "", width: int = 0) -> str:
    """Reindents text by dedenting and optionally wrapping paragraphs"""
    paragraphs = (
        " ".join(textwrap.dedent("\n".join(g)).splitlines())
        for b, g in itertools.groupby(s.splitlines(), bool)
        if b
    )
    if width and prefix:
        width -= len(prefix) + 1
        assert width > 0
    wrapped = "\n\n".join(
        textwrap.fill(p, width=width) if width else p for p in paragraphs
    )
    if not prefix:
        return wrapped
    return "\n".join(
        f"{prefix} {t}" if t else prefix for t in wrapped.splitlines()
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


def _tagged(text: str, /, **kwargs) -> str:
    tags = [f"{key}={val}" for key, val in kwargs.items() if val is not None]
    return f"{text} [{', '.join(tags)}]" if tags else text


class Progress:
    """Progress feedback interface"""

    def report(self, text: str, **tags) -> None:  # pragma: no cover
        raise NotImplementedError()

    def spinner(
        self, text: str, **tags
    ) -> contextlib.AbstractContextManager[
        ProgressSpinner
    ]:  # pragma: no cover
        raise NotImplementedError()

    @staticmethod
    def dynamic() -> Progress:
        """Progress suitable for interactive terminals"""
        return _DynamicProgress()

    @staticmethod
    def static() -> Progress:
        """Progress suitable for pipes, etc."""
        return _StaticProgress()


class ProgressSpinner:
    """Operation progress tracker"""

    @contextlib.contextmanager
    def hidden(self) -> Iterator[None]:
        yield None

    def update(self, text: str, **tags) -> None:  # pragma: no cover
        raise NotImplementedError()


class _DynamicProgress(Progress):
    def __init__(self) -> None:
        self._spinner: _DynamicProgressSpinner | None = None

    def report(self, text: str, **tags) -> None:
        message = f"☞ {_tagged(text, **tags)}"
        if self._spinner:
            self._spinner.yaspin.write(message)
        else:
            print(message)  # noqa

    @contextlib.contextmanager
    def spinner(self, text: str, **tags) -> Iterator[ProgressSpinner]:
        assert not self._spinner
        with yaspin.yaspin(text=_tagged(text, **tags)) as spinner:
            self._spinner = _DynamicProgressSpinner(spinner)
            try:
                yield self._spinner
            except Exception:
                self._spinner.yaspin.fail("✗")
                raise
            else:
                self._spinner.yaspin.ok("✓")
            finally:
                self._spinner = None


class _DynamicProgressSpinner(ProgressSpinner):
    def __init__(self, yaspin: yaspin.core.Yaspin) -> None:
        self.yaspin = yaspin

    @contextlib.contextmanager
    def hidden(self) -> Iterator[None]:
        with self.yaspin.hidden():
            yield

    def update(self, text: str, **tags) -> None:
        self.yaspin.text = _tagged(text, **tags)


class _StaticProgress(Progress):
    def report(self, text: str, **tags) -> None:
        print(_tagged(text, **tags))  # noqa

    @contextlib.contextmanager
    def spinner(self, text: str, **tags) -> Iterator[ProgressSpinner]:
        self.report(text, **tags)
        yield _StaticProgressSpinner(self)


class _StaticProgressSpinner(ProgressSpinner):
    def __init__(self, progress: _StaticProgress) -> None:
        self._progress = progress

    def update(self, text: str, **tags) -> None:
        self._progress.report(text, **tags)
