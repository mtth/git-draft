"""Event types related to user feedback interactions"""

from .common import EventStruct


class NotifyUser(EventStruct):
    """Generic user notification"""

    update: str


class RequestUserGuidance(EventStruct):
    """Additional information is requested from the user"""

    question: str


class ReceiveUserGuidance(EventStruct):
    """Response provided by the user"""

    answer: str
