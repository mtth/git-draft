"""TODO"""

from .common import Event


class NotifyUser(Event, frozen=True):
    """TODO"""

    contents: str


class RequestUserGuidance(Event, frozen=True):
    """TODO"""

    question: str


class ReceiveUserGuidance(Event, frozen=True):
    """TODO"""

    answer: str
