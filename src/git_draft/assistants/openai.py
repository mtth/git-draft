import openai
from typing import Any, Mapping, Sequence, override

from .common import Assistant, Session, Toolbox


def _function_tool_param(
    *,
    name: str,
    description: str,
    inputs: Mapping[str, Any] | None = None,
    required_inputs: Sequence[str] | None = None,
) -> openai.types.beta.FunctionToolParam:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": inputs or {},
                "required": required_inputs or [],
            },
            "strict": True,
        },
    }


_tools = [
    _function_tool_param(
        name="list_files",
        description="List all available files",
    ),
    _function_tool_param(
        name="read_file",
        description="Get a file's contents",
        inputs={
            "path": {
                "type": "string",
                "description": "Path of the file to be read",
            },
        },
        required_inputs=["path"],
    ),
    _function_tool_param(
        name="write_file",
        description="Update a file's contents",
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
        required_inputs=["path", "contents"],
    ),
]


# https://aider.chat/docs/more-info.html
# https://github.com/Aider-AI/aider/blob/main/aider/prompts.py
_INSTRUCTIONS = """\
    You are an expert software engineer, who writes correct and concise code.
    Use the provided functions to find the filesyou need to answer the query,
    read the content of the relevant ones, and save the changes you suggest.
"""


class OpenAIAssistant(Assistant):
    """An OpenAI-backed assistant

    See the following links for resources:

    * https://platform.openai.com/docs/assistants/tools/function-calling
    * https://platform.openai.com/docs/assistants/deep-dive#runs-and-run-steps
    * https://github.com/openai/openai-python/blob/main/src/openai/resources/beta/threads/runs/runs.py
    """

    def __init__(self) -> None:
        self._client = openai.OpenAI()

    def run(self, prompt: str, toolbox: Toolbox) -> Session:
        assistant = self._client.beta.assistants.create(
            instructions=_INSTRUCTIONS,
            model="gpt-4o",
            tools=_tools,
        )
        thread = self._client.beta.threads.create()

        message = self._client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt,
        )
        print(message)

        with self._client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant.id,
            event_handler=_EventHandler(self._client, toolbox),
        ) as stream:
            stream.until_done()

        return Session(0)


class _EventHandler(openai.AssistantEventHandler):
    def __init__(self, client: openai.Client, toolbox: Toolbox) -> None:
        self._client = client
        self._toolbox = toolbox

    @override
    def on_event(self, event: Any) -> None:
        if event.event == "thread.run.requires_action":
            run_id = event.data.id  # Retrieve the run ID from the event data
            self._handle_action(event.data, run_id)
        # TODO: Handle (log?) other events.

    def _handle_action(self, run_id: str, data: Any) -> None:
        tool_outputs = list[Any]()
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            print(tool)
            if tool.function.name == "read_file":
                raise NotImplementedError()  # TODO
                output = self._toolbox.read_file(tool)
                tool_outputs.append(
                    {"tool_call_id": tool.id, "output": output}
                )
            elif tool.function.name == "write_file":
                raise NotImplementedError()  # TODO
                tool_outputs.append({"tool_call_id": tool.id, "output": "OK"})

        run = self.current_run
        assert run, "No ongoing run"
        with self._client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=run.thread_id,
            run_id=run.id,
            tool_outputs=tool_outputs,
            event_handler=self,
        ) as stream:
            stream.until_done()
