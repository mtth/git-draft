"""CLI interactive editing utilities"""

import os
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


def _get_tty_filename():
    return "CON:" if sys.platform == "win32" else "/dev/tty"


def open_editor(placeholder="", *, _open_tty=open) -> str:
    """Open an editor to edit a file and return its contents

    The method returns once the editor is closed. It respects the `$EDITOR`
    environment variable.
    """
    with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
        binpath = _guess_editor_binpath()
        if not binpath:
            raise ValueError("Editor unavailable")

        if placeholder:
            with open(temp.name, "w") as writer:
                writer.write(placeholder)

        stdout = _open_tty(_get_tty_filename(), "wb")
        proc = subprocess.Popen(
            [binpath, temp.name], close_fds=True, stdout=stdout
        )
        proc.communicate()

        with open(temp.name, mode="r") as reader:
            return reader.read()
