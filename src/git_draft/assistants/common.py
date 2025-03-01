from __future__ import annotations

import dataclasses
from pathlib import PurePosixPath
from typing import Protocol, Sequence


class Toolbox(Protocol):
    def list_files(self) -> Sequence[PurePosixPath]: ...
    def read_file(self, path: PurePosixPath) -> str: ...
    def write_file(self, path: PurePosixPath, data: str) -> None: ...


@dataclasses.dataclass(frozen=True)
class Session:
    token_count: int


class Assistant:
    def run(self, prompt: str, toolbox: Toolbox) -> Session:
        raise NotImplementedError()
