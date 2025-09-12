"""Git-friendly code assistant"""

import logging

from .bots import ActionSummary, Bot, Goal, UserFeedback, Worktree


__all__ = [
    "ActionSummary",
    "Bot",
    "Goal",
    "UserFeedback",
    "Worktree",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
