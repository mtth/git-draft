"""Event types related to user feedback interactions"""

from .common import EventStruct


class NotifyUser(EventStruct, frozen=True):
    """Generic user notification"""

    contents: str


class RequestUserGuidance(EventStruct, frozen=True):
    """Additional information is requested from the user"""

    question: str


class ReceiveUserGuidance(EventStruct, frozen=True):
    """Response provided by the user"""

    answer: str
