from __future__ import annotations

import contextlib
import functools
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import string
import sys
import tempfile
from typing import ContextManager
import xdg_base_dirs


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
    if sys.platform == "win32":
        return "CON:"
    return "/dev/tty"


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


NAMESPACE = "git-draft"


def _ensure_state_home() -> Path:
    path = xdg_base_dirs.xdg_state_home() / NAMESPACE
    path.mkdir(parents=True, exist_ok=True)
    return path


class Store:
    _name = "db.v1.sqlite3"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._connection = conn

    @classmethod
    def persistent(cls) -> Store:
        path = _ensure_state_home() / cls._name
        conn = sqlite3.connect(str(path), autocommit=False)
        return cls(conn)

    @classmethod
    def in_memory(cls) -> Store:
        return cls(sqlite3.connect(":memory:"))

    def cursor(self) -> ContextManager[sqlite3.Cursor]:
        return contextlib.closing(self._connection.cursor())


_query_root = Path(__file__).parent / "queries"


@functools.cache
def sql(name: str) -> str:
    path = _query_root / f"{name}.sql"
    with open(path) as reader:
        return reader.read()


_random = random.Random()
_alphabet = string.ascii_lowercase + string.digits


def random_id(n: int) -> str:
    return "".join(_random.choices(_alphabet, k=n))
