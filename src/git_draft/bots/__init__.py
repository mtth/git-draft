"""Bot interfaces and built-in implementations

* https://aider.chat/docs/leaderboards/
"""

from typing import Any, Mapping

from .common import Action, Bot, Toolbox

__all__ = [
    "Action",
    "Bot",
    "Toolbox",
]


def load_bot(entry: str, kwargs: Mapping[str, Any]) -> Bot:
    if entry == "openai":
        return _load_openai_bot(**kwargs)
    raise NotImplementedError()  # TODO


def _load_openai_bot(**kwargs) -> Bot:
    from .openai import OpenAIBot

    return OpenAIBot(**kwargs)
