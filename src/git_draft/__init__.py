"""Git-friendly code assistant"""

import logging

from .bots import Action, Bot, Goal, UserFeedback, Worktree


__all__ = [
    "Action",
    "Bot",
    "Goal",
    "UserFeedback",
    "Worktree",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
