"""Bot interfaces and built-in implementations

* https://aider.chat/docs/leaderboards/
"""

import importlib
import os
import sys

from ..common import BotConfig, reindent
from ..toolbox import Toolbox
from .common import Action, Bot, Goal


__all__ = [
    "Action",
    "Bot",
    "Goal",
    "Toolbox",
]


def load_bot(config: BotConfig | None) -> Bot:
    """Load and return a Bot instance using the provided configuration"""
    if not config:
        return _default_bot()

    if config.pythonpath and config.pythonpath not in sys.path:
        sys.path.insert(0, config.pythonpath)

    parts = config.factory.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid bot factory: {config.factory}")
    module_name, symbol = parts
    module = importlib.import_module(module_name)

    factory = getattr(module, symbol, None)
    if not factory:
        raise NotImplementedError(f"Unknown bot factory: {config.factory}")

    kwargs = config.config or {}
    return factory(**kwargs)


def _default_bot() -> Bot:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            reindent(
                """
                    The default bot implementation requires an OpenAI API key.
                    Please specify one via the `$OPENAI_API_KEY` environment
                    variable or enable a different bot in your configuration.
                """
            )
        )

    try:
        from .openai import threads_bot

    except ImportError:
        raise RuntimeError(
            reindent(
                """
                    The default bot implementation requires the `openai` Python
                    package. Please install it or specify a different bot in
                    your configuration.
                """
            )
        )
    else:
        return threads_bot()
