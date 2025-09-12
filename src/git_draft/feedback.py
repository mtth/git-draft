"""User feedback implementations"""

from typing import override

from .bots import UserFeedback
from .common import reindent


_offline_answer = reindent("""
    I'm unable to provide feedback at this time. Perform any final changes and
    await further instructions.
""")


class Feedback(UserFeedback):
    """TODO"""

    def __init__(self) -> None:
        self.pending_question: str | None = None


class InteractiveFeedback(Feedback):
    """User feedback interface"""

    @override
    def notify(self, update: str) -> None:
        raise NotImplementedError()  # TODO: Implement

    @override
    def ask(self, question: str) -> str:
        raise NotImplementedError()  # TODO: Implement


class BatchFeedback(Feedback):
    """TODO"""

    @override
    def notify(self, update: str) -> None:
        pass

    @override
    def ask(self, question: str) -> str:
        assert not self.pending_question
        self.pending_question = question
        return _offline_answer
