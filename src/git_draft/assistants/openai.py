import openai
from pathlib import PurePosixPath

from .common import Assistant, Session, Toolbox


# https://aider.chat/docs/more-info.html
# https://github.com/Aider-AI/aider/blob/main/aider/prompts.py
_INSTRUCTIONS = """\
    You are an expert software engineer, who writes correct and concise code.
"""

_tools = [  # TODO
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Get a file's contents",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be read",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Update a file's contents",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path of the file to be updated",
                    },
                    "contents": {
                        "type": "string",
                        "description": "New contents of the file",
                    },
                },
                "required": ["path", "contents"],
            },
        },
    },
]


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
        # TODO: Switch to the thread run API, using tools to leverage toolbox
        # methods.
        # assistant = client.beta.assistants.create(
        #     instructions=_INSTRUCTIONS,
        #     model="gpt-4o",
        #     tools=_tools,
        # )
        # thread = client.beta.threads.create()
        # message = client.beta.threads.messages.create(
        #     thread_id=thread.id,
        #     role="user",
        #     content="What's the weather in San Francisco today and the likelihood it'll rain?",
        # )
        completion = self._client.chat.completions.create(
            messages=[
                {"role": "system", "content": _INSTRUCTIONS},
                {"role": "user", "content": prompt},
            ],
            model="gpt-4o",
        )
        content = completion.choices[0].message.content or ""
        toolbox.write_file(PurePosixPath(f"{completion.id}.txt"), content)
        return Session(0)
