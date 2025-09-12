"""TODO"""

from collections.abc import Sequence
from pathlib import PurePosixPath

from .common import EventStruct


class ListFiles(EventStruct, frozen=True):
    """TODO"""

    paths: Sequence[PurePosixPath]


class ReadFile(EventStruct, frozen=True):
    """TODO"""

    path: PurePosixPath
    contents: str | None


class WriteFile(EventStruct, frozen=True):
    """TODO"""

    path: PurePosixPath
    contents: str


class DeleteFile(EventStruct, frozen=True):
    """TODO"""

    path: PurePosixPath


class RenameFile(EventStruct, frozen=True):
    """TODO"""

    src_path: PurePosixPath
    dst_path: PurePosixPath


class StartEditingFiles(EventStruct, frozen=True):
    """TODO"""


class StopEditingFiles(EventStruct, frozen=True):
    """TODO"""
