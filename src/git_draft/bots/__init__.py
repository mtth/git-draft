"""Bot interfaces and built-in implementations"""

from collections.abc import Sequence
import importlib
import sys

from ..common import (
    BotConfig,
    JSONObject,
    JSONValue,
    UnreachableError,
    reindent,
)
from .common import ActionSummary, Bot, Goal, UserFeedback, Worktree


__all__ = [
    "ActionSummary",
    "Bot",
    "Goal",
    "UserFeedback",
    "Worktree",
]


def load_bot(
    config: BotConfig | None, *, overrides: Sequence[str] = ()
) -> Bot:
    """Load and return a Bot instance using the provided configuration"""
    options = {**config.options} if config and config.options else {}
    options.update(_parse_overrides(overrides))

    if not config:
        return _default_bot(options)

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

    return factory(**options)


def _parse_overrides(overrides: Sequence[str]) -> JSONObject:
    options = dict[str, JSONValue]()
    for override in overrides:
        match override.split("=", 1):
            case [switch]:
                options[switch] = True
            case [flag, value]:
                options[flag] = value
            case _:
                raise UnreachableError()
    return options


def _default_bot(options: JSONObject) -> Bot:
    try:
        from .openai_api import new_completions_bot

    except ImportError:
        raise RuntimeError(
            reindent("""
                The default bot implementation requires the `openai` Python
                package. Please install it or specify a different bot in
                your configuration.
            """)
        )
    else:
        return new_completions_bot(**options)
