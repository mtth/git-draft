from __future__ import annotations

import dataclasses
import openai
from pathlib import PurePosixPath
import textwrap
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
    def run(self, prompt: str, toolbox: Toolbox) -> BackendRun:
        raise NotImplementedError()


# https://aider.chat/docs/more-info.html
# https://github.com/Aider-AI/aider/blob/main/aider/prompts.py
_SYSTEM_PROMPT = textwrap.dedent(
    """
    You are an expert software engineer, who writes correct and concise code.
"""
)


class OpenAIBackend(Backend):
    def __init__(self) -> None:
        self._client = openai.OpenAI()

    def run(self, prompt: str, toolbox: Toolbox) -> BackendRun:
        # TODO: Switch to the thread run API, using tools to leverage toolbox
        # methods.
        # https://platform.openai.com/docs/assistants/deep-dive#runs-and-run-steps
        # https://github.com/openai/openai-python/blob/main/src/openai/resources/beta/threads/runs/runs.py
        completion = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o",
        )
        content = completion.choices[0].message.content or ""
        toolbox.write_file(PurePosixPath(f"{completion.id}.txt"), content)
        return BackendRun(0, calls=[BackendCall(completion.usage)])
