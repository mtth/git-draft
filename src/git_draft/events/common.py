"""Common event utilities"""

import types
from typing import Any, dataclass_transform

import msgspec


events = types.SimpleNamespace()


@dataclass_transform(field_specifiers=(msgspec.field,), frozen_default=True)
class EventStruct(msgspec.Struct, frozen=True):
    """Base immutable structure for all event types"""

    def __init_subclass__(cls, *args: Any, **kwargs) -> None:
        super().__init_subclass__(*args, **kwargs)
        setattr(events, cls.__name__, cls)
