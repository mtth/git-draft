from __future__ import annotations

import dataclasses
import openai
from pathlib import PurePosixPath
from typing import Protocol, Sequence


class Toolbox(Protocol):
    def list_files(self) -> Sequence[PurePosixPath]: ...
    def read_file(self, path: PurePosixPath) -> str: ...
    def write_file(self, path: PurePosixPath, data: str) -> None: ...


@dataclasses.dataclass(frozen=True)
class BackendRun:
    token_count: int
    calls: list[BackendCall]


@dataclasses.dataclass(frozen=True)
class BackendCall:
    usage: openai.types.CompletionUsage | None


class Backend:
    def call(self, prompt: str, toolbox: Toolbox) -> BackendRun:
        raise NotImplementedError()


class NewFileBackend(Backend):
    def run(self, prompt: str, toolbox: Toolbox) -> BackendRun:
        # send request to backend...
        import time

        time.sleep(2)

        # Add files to index.
        import random

        name = f"foo-{random.randint(1, 100)}"
        toolbox.write_file(PurePosixPath(name), prompt)

        return BackendRun(0, [])


class OpenAIBackend(Backend):
    def __init__(self) -> None:
        self._client = openai.OpenAI()

    def call(self, prompt: str, toolbox: Toolbox) -> BackendRun:
        completion = self._client.chat.completions.create(
            messages=[
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o",
        )
        content = completion.choices[0].message.content or ""
        toolbox.write_file(PurePosixPath(f"{completion.id}.txt"), content)
        return BackendRun(0, calls=[BackendCall(completion.usage)])
