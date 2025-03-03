import importlib
import sys
import pytest

from git_draft.bots import Bot, load_bot
from git_draft.common import BotConfig


class FakeBot(Bot):
    pass


class TestLoadBot:
    def test_existing_factory(self, monkeypatch) -> None:
        def import_module(name):
            assert name == "fake_module"
            return sys.modules[__name__]

        monkeypatch.setattr(importlib, "import_module", import_module)

        config = BotConfig(factory="fake_module:FakeBot")
        bot = load_bot(config)
        assert isinstance(bot, FakeBot)

    def test_non_existing_factory(self) -> None:
        config = BotConfig("git_draft:unknown_factory")
        with pytest.raises(NotImplementedError):
            load_bot(config)
