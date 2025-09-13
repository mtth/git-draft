"""Event types related to worktree file operations"""

from collections.abc import Sequence
from pathlib import PurePosixPath

from .common import EventStruct


class ListFiles(EventStruct):
    """All files were listed"""

    paths: Sequence[PurePosixPath]


class ReadFile(EventStruct):
    """A file was read"""

    path: PurePosixPath
    contents: str | None


class WriteFile(EventStruct):
    """A file was written"""

    path: PurePosixPath
    contents: str


class DeleteFile(EventStruct):
    """A file was deleted"""

    path: PurePosixPath


class RenameFile(EventStruct):
    """A file was renamed"""

    src_path: PurePosixPath
    dst_path: PurePosixPath


class StartEditingFiles(EventStruct):
    """A temporary editable copy of all files was opened"""


class StopEditingFiles(EventStruct):
    """The editable copy was closed"""
