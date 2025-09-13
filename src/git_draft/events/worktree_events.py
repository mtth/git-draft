"""Event types related to worktree file operations"""

from pathlib import PurePosixPath

from .common import EventStruct


class ListFiles(EventStruct):
    """All files were listed"""

    path_count: int


class ReadFile(EventStruct):
    """A file was read"""

    path: PurePosixPath
    char_count: int | None


class WriteFile(EventStruct):
    """A file was written"""

    path: PurePosixPath
    char_count: int


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
