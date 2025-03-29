"""CLI interactive editing utilities"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


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


def _get_tty_filename() -> str:
    return "CON:" if sys.platform == "win32" else "/dev/tty"


def open_editor(
    text: str = "",
    path: Path | None = None,
    *,
    _open_tty=open,  # noqa
) -> str:
    """Open an editor to edit a file and return its contents

    The method returns once the editor is closed. It respects the `$EDITOR`
    environment variable.
    """

    def edit(path: str) -> str:
        binpath = _guess_editor_binpath()
        if not binpath:
            raise ValueError("Editor unavailable")

        if text:
            with open(path, "w") as writer:
                writer.write(text)

        stdout = _open_tty(_get_tty_filename(), "wb")
        proc = subprocess.Popen([binpath, path], close_fds=True, stdout=stdout)
        proc.communicate()

        with open(path) as reader:
            return reader.read()

    if path:
        return edit(str(path))
    else:
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            return edit(temp.name)
