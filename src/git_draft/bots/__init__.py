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
    """Load and return a Bot instance using the provided configuration.

    If a pythonpath is specified in the config and not already present in
    sys.path, it is added. The function expects the config.factory in the
    format 'module:symbol' or 'symbol'. If only 'symbol' is provided, the
    current module is used.

    Args:
        config: BotConfig object containing bot configuration details.

    Raises:
        NotImplementedError: If the specified factory cannot be found.
    """
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
    """Instantiate and return an OpenAIBot with provided keyword arguments.

    This function imports the OpenAIBot class from the openai module and
    returns an instance configured with the provided arguments.

    Args:
        **kwargs: Arbitrary keyword arguments used to configure the bot.
    """
    from .openai import OpenAIBot

    return OpenAIBot(**kwargs)
