import importlib
import sys

import pytest

import git_draft.bots as sut
from git_draft.common import BotConfig


class FakeBot(sut.Bot):
    def __init__(self, key: str="default", switch: bool=False) -> None:
        self.key = key
        self.switch = switch


class TestLoadBot:
    def test_existing_factory(self, monkeypatch) -> None:
        def import_module(name):
            assert name == "fake_module"
            return sys.modules[__name__]

        monkeypatch.setattr(importlib, "import_module", import_module)

        config = BotConfig(factory="fake_module:FakeBot")

        bot0 = sut.load_bot(config)
        assert isinstance(bot0, FakeBot)
        assert bot0.key == "default"
        assert not bot0.switch

        bot1 = sut.load_bot(config, overrides=["key=one", "switch"])
        assert isinstance(bot1, FakeBot)
        assert bot1.key == "one"
        assert bot1.switch


    def test_non_existing_factory(self) -> None:
        config = BotConfig("git_draft:unknown_factory")
        with pytest.raises(NotImplementedError):
            sut.load_bot(config)

    def test_default_no_key(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "")
        with pytest.raises(RuntimeError):
            sut.load_bot(None)
