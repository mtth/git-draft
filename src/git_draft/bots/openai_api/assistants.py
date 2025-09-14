"""Assistants API implementation

Note that this API is (will soon?) be deprecated in favor of the responses API.
It does not support the gpt-5 series of models.
"""

from collections.abc import Sequence
import logging
from pathlib import PurePosixPath
from typing import Any, Self, TypedDict, override

import openai

from ...common import JSONObject
from ...instructions import SYSTEM_PROMPT
from ..common import ActionSummary, Bot, Goal, UserFeedback, Worktree
from .common import ToolHandler, ToolsFactory, new_client


_logger = logging.getLogger(__name__)


def new_threads_bot(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "gpt-4o",
) -> Bot:
    """Beta bot, uses assistant threads with function calling"""
    return _ThreadsBot(new_client(api_key, base_url), model)


class _ThreadsBot(Bot):
    def __init__(self, client: openai.OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def _load_assistant_id(self) -> str:
        kwargs: JSONObject = dict(
            model=self._model,
            instructions=SYSTEM_PROMPT,
            tools=ToolsFactory(strict=True).params(),
        )
        path = self.state_folder_path(ensure_exists=True) / "ASSISTANT_ID"
        try:
            with open(path) as f:
                assistant_id = f.read()
            self._client.beta.assistants.update(assistant_id, **kwargs)
        except (FileNotFoundError, openai.NotFoundError):
            assistant = self._client.beta.assistants.create(**kwargs)
            assistant_id = assistant.id
            with open(path, "w") as f:
                f.write(assistant_id)
        return assistant_id

    async def act(
        self, goal: Goal, tree: Worktree, feedback: UserFeedback
    ) -> ActionSummary:
        assistant_id = self._load_assistant_id()

        thread = self._client.beta.threads.create()
        self._client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=goal.prompt,
        )

        # We intentionally do not count the two requests above, to focus on
        # "data requests" only.
        action = ActionSummary(request_count=0, token_count=0)
        with self._client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant_id,
            event_handler=_EventHandler(self._client, tree, feedback, action),
        ) as stream:
            stream.until_done()
        return action


class _EventHandler(openai.AssistantEventHandler):
    def __init__(
        self,
        client: openai.Client,
        tree: Worktree,
        feedback: UserFeedback,
        action: ActionSummary,
    ) -> None:
        super().__init__()
        self._client = client
        self._tree = tree
        self._feedback = feedback
        self._action = action
        self._action.increment_request_count()

    def _clone(self) -> Self:
        return self.__class__(
            self._client, self._tree, self._feedback, self._action
        )

    @override
    def on_event(self, event: openai.types.beta.AssistantStreamEvent) -> None:
        if event.event == "thread.run.requires_action":
            run_id = event.data.id  # Retrieve the run ID from the event data
            self._handle_action(run_id, event.data)
        elif event.event == "thread.run.completed":
            _logger.info("Threads run completed. [usage=%s]", event.data.usage)
        else:
            _logger.debug("Threads event: %s", event)

    @override
    def on_run_step_done(
        self, run_step: openai.types.beta.threads.runs.RunStep
    ) -> None:
        usage = run_step.usage
        if usage:
            _logger.debug("Threads run step usage: %s", usage)
            self._action.increment_token_count(usage.total_tokens)
        else:
            _logger.warning("Missing usage in threads run step")

    def _handle_action(self, _run_id: str, data: Any) -> None:
        tool_outputs = list[Any]()
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            handler = _ThreadToolHandler(self._tree, self._feedback, tool.id)
            tool_outputs.append(handler.handle_function(tool.function))

        run = self.current_run
        assert run, "No ongoing run"
        with self._client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=run.thread_id,
            run_id=run.id,
            tool_outputs=tool_outputs,
            event_handler=self._clone(),
        ) as stream:
            stream.until_done()


class _ToolOutput(TypedDict):
    tool_call_id: str
    output: str


class _ThreadToolHandler(ToolHandler[_ToolOutput]):
    def __init__(
        self, tree: Worktree, feedback: UserFeedback, call_id: str
    ) -> None:
        super().__init__(tree, feedback)
        self._call_id = call_id

    def _wrap(self, output: str) -> _ToolOutput:
        return _ToolOutput(tool_call_id=self._call_id, output=output)

    def _on_ask_user(self, response: str) -> _ToolOutput:
        return self._wrap(response)

    def _on_read_file(
        self, _path: PurePosixPath, contents: str | None
    ) -> _ToolOutput:
        return self._wrap(contents or "")

    def _on_write_file(self, _path: PurePosixPath) -> _ToolOutput:
        return self._wrap("OK")

    def _on_delete_file(self, _path: PurePosixPath) -> _ToolOutput:
        return self._wrap("OK")

    def _on_rename_file(
        self, _src_path: PurePosixPath, _dst_path: PurePosixPath
    ) -> _ToolOutput:
        return self._wrap("OK")

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> _ToolOutput:
        return self._wrap("\n".join(str(p) for p in paths))
