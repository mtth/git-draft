from __future__ import annotations

import dataclasses
from pathlib import PurePosixPath
from typing import Protocol, Sequence


class Toolbox(Protocol):
    # TODO: Something similar to https://aider.chat/docs/repomap.html,
    # including inferring the most important files, and allowing returning
    # signature-only versions.

    def list_files(self) -> Sequence[PurePosixPath]: ...

    def read_file(self, path: PurePosixPath) -> str: ...

    def write_file(
        self,
        path: PurePosixPath,
        contents: str,
        change_description: str | None = None,
    ) -> None: ...


@dataclasses.dataclass(frozen=True)
class Session:
    token_count: int


class Bot:
    def run(self, prompt: str, toolbox: Toolbox) -> Session:
        raise NotImplementedError()
