"""TODO"""

from collections.abc import Iterator
from pathlib import PurePosixPath
import types
from typing import Any, Protocol

import msgspec

from . import feedback_events, worktree_events
from .common import EventStruct


type Event = (
    worktree_events.ListFiles
    | worktree_events.ReadFile
    | worktree_events.WriteFile
    | worktree_events.DeleteFile
    | worktree_events.RenameFile
    | worktree_events.StartEditingFiles
    | worktree_events.StopEditingFiles
    | feedback_events.NotifyUser
    | feedback_events.RequestUserGuidance
    | feedback_events.ReceiveUserGuidance
)


def _classes(*modules: types.ModuleType) -> Iterator[tuple[str, type]]:
    for mod in modules:
        for key, val in vars(mod).items():
            try:
                if issubclass(val, EventStruct) and val is not EventStruct:
                    yield key, val
            except TypeError:
                pass


events = types.SimpleNamespace(_classes(feedback_events, worktree_events))


class EventConsumer(Protocol):
    """TODO"""

    def on_event(self, event: Event) -> None:
        pass


def event_encoder() -> msgspec.json.Encoder:
    return msgspec.json.Encoder(enc_hook=_enc_hook)


def _enc_hook(obj: Any) -> Any:
    assert isinstance(obj, PurePosixPath)
    return str(obj)


def event_decoder() -> msgspec.json.Decoder:
    """Returns a decoder for event instances

    It should be used as follows to get typed values:

        decoder.decode(data, type=events[class_name])

    """
    return msgspec.json.Decoder(dec_hook=_dec_hook)


def _dec_hook(tp: type, obj: Any) -> Any:
    assert tp is PurePosixPath and isinstance(obj, str)
    return PurePosixPath(obj)
