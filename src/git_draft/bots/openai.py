"""OpenAI API-backed bots

They can be used with services other than OpenAPI as long as them implement a
sufficient subset of the API. For example the `completions_bot` only requires
tools support.

See the following links for more resources:

* https://platform.openai.com/docs/assistants/tools/function-calling
* https://platform.openai.com/docs/assistants/deep-dive#runs-and-run-steps
* https://platform.openai.com/docs/api-reference/assistants-streaming/events
* https://github.com/openai/openai-python/blob/main/src/openai/resources/beta/threads/runs/runs.py
"""

from collections.abc import Mapping, Sequence
import json
import logging
import os
from pathlib import PurePosixPath
from typing import Any, Self, TypedDict, override

import openai

from ..common import JSONObject, reindent
from .common import Action, Bot, Goal, Toolbox


_logger = logging.getLogger(__name__)


_DEFAULT_MODEL = "gpt-4o"


def completions_bot(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> Bot:
    """Compatibility-mode bot, uses completions with function calling"""
    if api_key and api_key.startswith("$"):
        api_key = os.environ[api_key[1:]]
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    return _CompletionsBot(client, model)


def threads_bot(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> Bot:
    """Beta bot, uses assistant threads with function calling"""
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    return _ThreadsBot.create(client, model)


class _ToolsFactory:
    def __init__(self, strict: bool) -> None:
        self._strict = strict

    def _param(
        self,
        name: str,
        description: str,
        inputs: Mapping[str, Any] | None = None,
        _required_inputs: Sequence[str] | None = None,
    ) -> openai.types.beta.FunctionToolParam:
        param: openai.types.beta.FunctionToolParam = {
            "type": "function",
            "function": {
                "name": name,
                "description": reindent(description),
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": inputs or {},
                    "required": list(inputs.keys()) if inputs else [],
                },
            },
        }
        if self._strict:
            param["function"]["strict"] = True
        return param

    def params(self) -> Sequence[openai.types.chat.ChatCompletionToolParam]:
        return [
            self._param(
                name="list_files",
                description="List all available files",
            ),
            self._param(
                name="read_file",
                description="Get a file's contents",
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be read",
                    },
                },
            ),
            self._param(
                name="write_file",
                description="""
                    Set a file's contents

                    The file will be created if it does not already exist.
                """,
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be updated",
                    },
                    "contents": {
                        "type": "string",
                        "description": "New contents of the file",
                    },
                },
            ),
            self._param(
                name="delete_file",
                description="Delete a file",
                inputs={
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be deleted",
                    },
                },
            ),
        ]


# https://aider.chat/docs/more-info.html
# https://github.com/Aider-AI/aider/blob/main/aider/prompts.py
_INSTRUCTIONS = """
    You are an expert software engineer, who writes correct and concise code.
    Use the provided functions to find the files you need to answer the query,
    read the content of the relevant ones, and save the changes you suggest.

    You should stop when and ONLY WHEN all the files you need to change have
    been updated. If you stop for any reason before completing your task,
    explain why by updating a REASON file before stopping. For example if you
    are missing some information or noticed something inconsistent with the
    instructions, say so there. DO NOT STOP without updating at least this
    file.
"""


class _ToolHandler[V]:
    def __init__(self, toolbox: Toolbox) -> None:
        self._toolbox = toolbox

    def _on_read_file(self, path: PurePosixPath, contents: str | None) -> V:
        raise NotImplementedError()

    def _on_write_file(self, path: PurePosixPath) -> V:
        raise NotImplementedError()

    def _on_delete_file(self, path: PurePosixPath) -> V:
        raise NotImplementedError()

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> V:
        raise NotImplementedError()

    def handle_function(self, function: Any) -> V:
        name = function.name
        inputs = json.loads(function.arguments)
        _logger.info("Requested function: %s", function)
        if name == "read_file":
            path = PurePosixPath(inputs["path"])
            return self._on_read_file(path, self._toolbox.read_file(path))
        elif name == "write_file":
            path = PurePosixPath(inputs["path"])
            contents = inputs["contents"]
            self._toolbox.write_file(path, contents)
            return self._on_write_file(path)
        elif name == "delete_file":
            path = PurePosixPath(inputs["path"])
            self._toolbox.delete_file(path)
            return self._on_delete_file(path)
        else:
            assert name == "list_files" and not inputs
            paths = self._toolbox.list_files()
            return self._on_list_files(paths)


class _CompletionsBot(Bot):
    def __init__(self, client: openai.OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        tools = _ToolsFactory(strict=False).params()
        tool_handler = _CompletionsToolHandler(toolbox)

        messages: list[openai.types.chat.ChatCompletionMessageParam] = [
            {"role": "system", "content": reindent(_INSTRUCTIONS)},
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
            request_count += 1

            done = True
            calls = response.choices[0].message.tool_calls
            for call in calls or []:
                output = tool_handler.handle_function(call.function)
                if output is not None:
                    done = False
                    messages.append({"role": "user", "content": output})
            if done:
                break

        return Action(request_count=request_count)


class _CompletionsToolHandler(_ToolHandler[str | None]):
    def _on_read_file(self, path: PurePosixPath, contents: str | None) -> str:
        if contents is None:
            return f"`{path}` does not exist."
        return f"The contents of `{path}` are:\n\n```\n{contents}\n```\n"

    def _on_write_file(self, _path: PurePosixPath) -> None:
        return None

    def _on_delete_file(self, _path: PurePosixPath) -> None:
        return None

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> str:
        joined = "\n".join(f"* {p}" for p in paths)
        return f"Here are the available files: {joined}"


class _ThreadsBot(Bot):
    def __init__(self, client: openai.OpenAI, assistant_id: str) -> None:
        self._client = client
        self._assistant_id = assistant_id

    @classmethod
    def create(cls, client: openai.OpenAI, model: str) -> Self:
        assistant_kwargs: JSONObject = dict(
            model=model,
            instructions=reindent(_INSTRUCTIONS),
            tools=_ToolsFactory(strict=True).params(),
        )

        path = cls.state_folder_path(ensure_exists=True) / "ASSISTANT_ID"
        try:
            with open(path) as f:
                assistant_id = f.read()
            client.beta.assistants.update(assistant_id, **assistant_kwargs)
        except (FileNotFoundError, openai.NotFoundError):
            assistant = client.beta.assistants.create(**assistant_kwargs)
            assistant_id = assistant.id
            with open(path, "w") as f:
                f.write(assistant_id)

        return cls(client, assistant_id)

    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        thread = self._client.beta.threads.create()
        self._client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=goal.prompt,
        )

        # We intentionally do not count the two requests above, to focus on
        # "data requests" only.
        action = Action(request_count=0, token_count=0)
        with self._client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=self._assistant_id,
            event_handler=_EventHandler(self._client, toolbox, action),
        ) as stream:
            stream.until_done()
        return action


class _EventHandler(openai.AssistantEventHandler):
    def __init__(
        self, client: openai.Client, toolbox: Toolbox, action: Action
    ) -> None:
        super().__init__()
        self._client = client
        self._toolbox = toolbox
        self._action = action
        self._action.increment_request_count()

    def _clone(self) -> Self:
        return self.__class__(self._client, self._toolbox, self._action)

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
            handler = _ThreadToolHandler(self._toolbox, tool.id)
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


class _ThreadToolHandler(_ToolHandler[_ToolOutput]):
    def __init__(self, toolbox: Toolbox, call_id: str) -> None:
        super().__init__(toolbox)
        self._call_id = call_id

    def _wrap(self, output: str) -> _ToolOutput:
        return _ToolOutput(tool_call_id=self._call_id, output=output)

    def _on_read_file(
        self, _path: PurePosixPath, contents: str | None
    ) -> _ToolOutput:
        return self._wrap(contents or "")

    def _on_write_file(self, _path: PurePosixPath) -> _ToolOutput:
        return self._wrap("OK")

    def _on_delete_file(self, _path: PurePosixPath) -> _ToolOutput:
        return self._wrap("OK")

    def _on_list_files(self, paths: Sequence[PurePosixPath]) -> _ToolOutput:
        return self._wrap("\n".join(str(p) for p in paths))
