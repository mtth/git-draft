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
    if len(parts) != 2:
        raise ValueError(f"Invalid bot factory: {config.factory}")
    module_name, symbol = parts
    module = importlib.import_module(module_name)

    factory = getattr(module, symbol, None)
    if not factory:
        raise NotImplementedError(f"Unknown bot factory: {factory}")

    kwargs = config.config or {}
    return factory(**kwargs)
