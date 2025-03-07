from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import PurePosixPath
import tempfile
from typing import Callable, Sequence, override

import git

from .common import JSONObject


class Toolbox:
    """File-system intermediary

    Note that the toolbox is not thread-safe. Concurrent operations should be
    serialized by the caller.
    """

    # TODO: Something similar to https://aider.chat/docs/repomap.html,
    # including inferring the most important files, and allowing returning
    # signature-only versions.

    # TODO: Support a diff-based edit method.
    # https://gist.github.com/noporpoise/16e731849eb1231e86d78f9dfeca3abc

    def __init__(self, hook: OperationHook | None = None) -> None:
        self.operations = list[Operation]()
        self._operation_hook = hook

    def _record_operation(
        self, reason: str | None, tool: str, **kwargs
    ) -> None:
        op = Operation(
            tool=tool, details=kwargs, reason=reason, start=datetime.now()
        )
        self.operations.append(op)
        if self._operation_hook:
            self._operation_hook(op)

    def list_files(self, reason: str | None = None) -> Sequence[PurePosixPath]:
        self._record_operation(reason, "list_files")
        return self._list()

    def read_file(
        self,
        path: PurePosixPath,
        reason: str | None = None,
    ) -> str | None:
        self._record_operation(reason, "read_file", path=str(path))
        try:
            return self._read(path)
        except FileNotFoundError:
            return None

    def write_file(
        self,
        path: PurePosixPath,
        contents: str,
        reason: str | None = None,
    ) -> None:
        self._record_operation(
            reason, "write_file", path=str(path), size=len(contents)
        )
        return self._write(path, contents)

    def delete_file(
        self,
        path: PurePosixPath,
        reason: str | None = None,
    ) -> None:
        self._record_operation(reason, "delete_file", path=str(path))
        return self._delete(path)

    def _list(self) -> Sequence[PurePosixPath]:
        raise NotImplementedError()

    def _read(self, path: PurePosixPath) -> str:
        raise NotImplementedError()

    def _write(self, path: PurePosixPath, contents: str) -> None:
        raise NotImplementedError()

    def _delete(self, path: PurePosixPath) -> None:
        raise NotImplementedError()


@dataclasses.dataclass(frozen=True)
class Operation:
    tool: str
    details: JSONObject
    reason: str | None
    start: datetime


type OperationHook = Callable[[Operation], None]


class StagingToolbox(Toolbox):
    """Git-index backed toolbox

    All files are directly read from and written to the index. This allows
    concurrent editing without interference.
    """

    def __init__(
        self, repo: git.Repo, hook: OperationHook | None = None
    ) -> None:
        super().__init__(hook)
        self._repo = repo
        self._written = set[str]()

    @override
    def _list(self) -> Sequence[PurePosixPath]:
        # Show staged files.
        return self._repo.git.ls_files().splitlines()

    @override
    def _read(self, path: PurePosixPath) -> str:
        # Read the file from the index.
        return self._repo.git.show(f":{path}")

    @override
    def _write(self, path: PurePosixPath, contents: str) -> None:
        self._written.add(str(path))
        # Update the index without touching the worktree.
        # https://stackoverflow.com/a/25352119
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            temp.write(contents.encode("utf8"))
            temp.close()
            sha = self._repo.git.hash_object("-w", temp.name, path=path)
            mode = 644  # TODO: Read from original file if it exists.
            self._repo.git.update_index(
                f"{mode},{sha},{path}", add=True, cacheinfo=True
            )

    def trim_index(self) -> None:
        diff = self._repo.git.diff(name_only=True, cached=True)
        untouched = [
            path
            for path in diff.splitlines()
            if path and path not in self._written
        ]
        if untouched:
            self._repo.git.reset("--", *untouched)
