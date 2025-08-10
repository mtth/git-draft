"""User feedback implementations"""

from typing import override

from .bots import UserFeedback
from .common import reindent


_offline_answer = reindent("""
    I'm unable to provide feedback at this time. Perform any final changes and
    await further instructions.
""")


class InteractiveUserFeedback(UserFeedback):
    """User feedback interface"""

    @override
    def notify(self, update: str) -> None:
        raise NotImplementedError()  # TODO: Implement

    @override
    def ask(self, question: str) -> str:
        raise NotImplementedError()  # TODO: Implement


class BatchUserFeedback(UserFeedback):
    """TODO"""

    def __init__(self) -> None:
        self.pending_questions = list[str]()

    @override
    def notify(self, update: str) -> None:
        pass

    @override
    def ask(self, question: str) -> str:
        self.pending_questions.append(question)
        return _offline_answer
