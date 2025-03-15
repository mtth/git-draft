"""Git-friendly code assistant"""

import logging

from .bots import Action, Bot, Goal, Toolbox


__all__ = [
    "Action",
    "Bot",
    "Goal",
    "Toolbox",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
