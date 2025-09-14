"""OpenAI API-backed bots

They can be used with services other than OpenAI as long as them implement a
sufficient subset of the API. For example the `completions_bot` only requires
tools support.

See the following links for more resources:

* https://platform.openai.com/docs/assistants/tools/function-calling
* https://platform.openai.com/docs/assistants/deep-dive#runs-and-run-steps
* https://platform.openai.com/docs/api-reference/assistants-streaming/events
* https://github.com/openai/openai-python/blob/main/src/openai/resources/beta/threads/runs/runs.py
"""

from .assistants import threads_bot
from .completions import completions_bot


__all__ = [
    "completions_bot",
    "threads_bot",
]
