"""TODO"""

import datetime

import msgspec


class Event(msgspec.Struct, frozen=True):
    """TODO"""

    at: datetime.datetime
