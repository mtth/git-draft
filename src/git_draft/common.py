from __future__ import annotations

import dataclasses
import logging
import os
from pathlib import Path
import random
import shutil
import subprocess
import string
import sys
import tempfile
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


_default_editors = ["vim", "emacs", "nano"]


def _guess_editor_binpath() -> str:
    editor = os.environ.get("EDITOR")
    if editor:
        return shutil.which(editor) or ""
    for editor in _default_editors:
        binpath = shutil.which(editor)
        if binpath:
            return binpath
    return ""


def _get_tty_filename():
    return "CON:" if sys.platform == "win32" else "/dev/tty"


def open_editor(placeholder="") -> str:
    with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
        binpath = _guess_editor_binpath()
        if not binpath:
            raise ValueError("Editor unavailable")

        if placeholder:
            with open(temp.name, "w") as writer:
                writer.write(placeholder)

        stdout = open(_get_tty_filename(), "wb")
        proc = subprocess.Popen(
            [binpath, temp.name], close_fds=True, stdout=stdout
        )
        proc.communicate()

        with open(temp.name, mode="r") as reader:
            return reader.read()


_random = random.Random()
_alphabet = string.ascii_lowercase + string.digits


def random_id(n: int) -> str:
    return "".join(_random.choices(_alphabet, k=n))


class UnreachableError(RuntimeError):
    pass
