"""TODO"""

from .common import EventStruct


class NotifyUser(EventStruct, frozen=True):
    """TODO"""

    contents: str


class RequestUserGuidance(EventStruct, frozen=True):
    """TODO"""

    question: str


class ReceiveUserGuidance(EventStruct, frozen=True):
    """TODO"""

    answer: str
