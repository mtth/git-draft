"""Miscellaneous utilities"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from datetime import datetime
import itertools
import logging
import os
from pathlib import Path
import textwrap
import tomllib
from typing import Any, Self

import xdg_base_dirs


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
    kwargs: JSONObject | None = None
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


def tagged(text: str, /, **kwargs) -> str:
    if kwargs:
        tags = [
            f"{key}={val}" for key, val in kwargs.items() if val is not None
        ]
        text = f"{text} [{', '.join(tags)}]" if tags else text
    return reindent(text)


def qualified_class_name(cls: type) -> str:
    name = cls.__qualname__
    return f"{cls.__module__}.{name}" if cls.__module__ else name


def now() -> datetime:
    return datetime.now().astimezone()
