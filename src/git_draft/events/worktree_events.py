"""TODO"""

from collections.abc import Sequence
from pathlib import PurePosixPath

from .common import Event


class ListFiles(Event, frozen=True):
    """TODO"""

    paths: Sequence[PurePosixPath]


class ReadFile(Event, frozen=True):
    """TODO"""

    path: PurePosixPath
    contents: str | None


class WriteFile(Event, frozen=True):
    """TODO"""

    path: PurePosixPath
    contents: str


class DeleteFile(Event, frozen=True):
    """TODO"""

    path: PurePosixPath


class RenameFile(Event, frozen=True):
    """TODO"""

    src_path: PurePosixPath
    dst_path: PurePosixPath


class StartEditingFiles(Event, frozen=True):
    """TODO"""


class StopEditingFiles(Event, frozen=True):
    """TODO"""
