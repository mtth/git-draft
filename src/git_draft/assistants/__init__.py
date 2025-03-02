"""Assistant interfaces and built-in implementations

* https://aider.chat/docs/leaderboards/
"""

from typing import Any, Mapping

from .common import Assistant, Session, Toolbox

__all__ = [
    "Assistant",
    "Session",
    "Toolbox",
]


def load_assistant(entry: str, kwargs: Mapping[str, Any]) -> Assistant:
    if entry == "openai":
        return _load_openai_assistant(**kwargs)
    raise NotImplementedError()  # TODO


def _load_openai_assistant(**kwargs) -> Assistant:
    from .openai import OpenAIAssistant

    return OpenAIAssistant(**kwargs)
