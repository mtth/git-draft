"""Chat completions API bot implementation"""

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any, cast

import openai

from ...instructions import SYSTEM_PROMPT
from ..common import ActionSummary, Bot, Goal, UserFeedback, Worktree
from .common import ToolHandler, ToolsFactory, new_client


def completions_bot(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "gpt-4o",
) -> Bot:
    """Compatibility-mode bot, uses completions with function calling"""
    return _CompletionsBot(new_client(api_key, base_url), model)


class _CompletionsBot(Bot):
    def __init__(self, client: openai.OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def act(
        self, goal: Goal, tree: Worktree, feedback: UserFeedback
    ) -> ActionSummary:
        tools = ToolsFactory(strict=False).params()
        tool_handler = _CompletionsToolHandler(tree, feedback)

        messages: list[openai.types.chat.ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": goal.prompt},
        ]

        request_count = 0
        while True:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="required",
            )
            assert len(response.choices) == 1
            choice = response.choices[0]
            request_count += 1

            done = True
            messages.append(cast(Any, choice.message.to_dict(mode="json")))
            calls = choice.message.tool_calls
            for call in calls or []:
                output = tool_handler.handle_function(call.function)
                if output is not None:
                    done = False
                    messages.append({"role": "user", "content": output})
            if done:
                break

        return ActionSummary(request_count=request_count)


class _CompletionsToolHandler(ToolHandler[str | None]):
    def _on_ask_user(self, response: str) -> str:
        return response

    def _on_read_file(self, path: PurePosixPath, contents: str | None) -> str:
        if contents is None:
            return f"`{path}` does not exist."
        return f"The contents of `{path}` are:\n\n```\n{contents}\n```\n"

    def _on_write_file(self, _path: PurePosixPath) -> None:
        return None

    def _on_delete_file(self, _path: PurePosixPath) -> None:
        return None

    def _on_rename_file(
        self, _src_path: PurePosixPath, _dst_path: PurePosixPath
    ) -> None:
        return None

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> str:
        joined = "\n".join(f"* {p}" for p in paths)
        return f"Here are the available files: {joined}"
