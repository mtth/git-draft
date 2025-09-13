from pathlib import PurePosixPath

from msgspec import json
import pytest

import git_draft.events as sut


class TestEventEncoder:
    @pytest.fixture
    def encoder(self):
        return sut.event_encoder()

    def test_encode_event(self, encoder):
        path = PurePosixPath("/some/path")
        event = sut.worktree_events.DeleteFile(path)
        result = encoder.encode(event)
        assert result == json.encode({"path": str(path)})


class TestEventDecoders:
    @pytest.fixture
    def decoders(self):
        return sut.event_decoders()

    def test_decoder_for_known_event(self, decoders):
        decoder = decoders["DeleteFile"]
        path_str = "/some/path"
        event = decoder.decode(json.encode({"path": path_str}))
        assert isinstance(event, sut.worktree_events.DeleteFile)
        assert event.path == PurePosixPath(path_str)

    def test_decoder_for_unknown_event_raises_keyerror(self, decoders):
        with pytest.raises(AttributeError):
            _ = decoders["NonExistentEvent"]
