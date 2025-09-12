"""Common event utilities"""

import datetime
import types
from typing import Any

import msgspec


events = types.SimpleNamespace()


class EventStruct(msgspec.Struct, frozen=True):
    """Base immutable structure for all event types"""

    at: datetime.datetime

    def __init_subclass__(cls, *args: Any, **kwargs) -> None:
        super().__init_subclass__(*args, **kwargs)
        setattr(events, cls.__name__, cls)
