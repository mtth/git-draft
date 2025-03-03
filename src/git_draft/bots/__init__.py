"""Bot interfaces and built-in implementations

* https://aider.chat/docs/leaderboards/
"""

import importlib
import sys

from ..common import BotConfig
from .common import Action, Bot, Operation, OperationHook, Toolbox

__all__ = [
    "Action",
    "Bot",
    "Operation",
    "OperationHook",
    "Toolbox",
]


def load_bot(config: BotConfig) -> Bot:
    if config.pythonpath and config.pythonpath not in sys.path:
        sys.path.insert(0, config.pythonpath)

    parts = config.factory.split(":", 1)
    if len(parts) == 1:
        module = sys.modules[__name__]  # Default to this module
        symbol = parts[0]
    else:
        module_name, symbol = parts
        module = importlib.import_module(module_name)

    factory = getattr(module, symbol, None)
    if not factory:
        raise NotImplementedError(f"Unknown factory: {factory}")

    kwargs = config.config or {}
    return factory(**kwargs)


def openai_bot(**kwargs) -> Bot:
    from .openai import OpenAIBot

    return OpenAIBot(**kwargs)
