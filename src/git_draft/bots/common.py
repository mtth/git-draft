from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

from ..common import JSONObject, ensure_state_home


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
    ) -> str:
        self._record_operation(reason, "read_file", path=str(path))
        return self._read(path)

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


@dataclasses.dataclass(frozen=True)
class Goal:
    prompt: str
    timeout: float | None


@dataclasses.dataclass(frozen=True)
class Action:
    title: str | None = None


class Bot:
    @classmethod
    def state_folder_path(cls, ensure_exists=False) -> Path:
        name = cls.__qualname__
        if cls.__module__:
            name = f"{cls.__module__}.{name}"
        path = ensure_state_home() / "bots" / name
        if ensure_exists:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        raise NotImplementedError()
