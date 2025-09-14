"""OpenAI API-backed bots

They can be used with services other than OpenAI as long as them implement a
sufficient subset of the API. For example the `new_completions_bot` only
requires tools support.
"""

from .assistants import new_threads_bot
from .completions import new_completions_bot


__all__ = [
    "new_completions_bot",
    "new_threads_bot",
]
