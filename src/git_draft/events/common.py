"""TODO"""

import datetime

import msgspec


class EventStruct(msgspec.Struct, frozen=True):
    """TODO"""

    at: datetime.datetime
