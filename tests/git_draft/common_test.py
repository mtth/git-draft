import logging
from pathlib import Path
import pytest
import textwrap

import git_draft.common as sut


def test_ensure_state_home() -> None:
    path = sut.ensure_state_home()
    assert path.exists()


class TestRandomId:
    def test_length(self) -> None:
        length = 10
        result = sut.random_id(length)
        assert len(result) == length

    def test_content(self) -> None:
        result = sut.random_id(1000)
        assert set(result).issubset(sut._alphabet)


class TestConfig:
    @pytest.fixture(autouse=True)
    def config_home(self, monkeypatch, tmp_path) -> Path:
        path = tmp_path / "config"
        monkeypatch.setattr(sut.xdg_base_dirs, "xdg_config_home", lambda: path)
        return path

    def test_load_ok(self) -> None:
        text = """\
            log_level = "DEBUG"

            [[bots]]
            factory = "foo:load"
            pythonpath = "./abc"

            [[bots]]
            name = "bar"
            factory = "bar"
            config = {one=1}
        """
        path = sut.Config.folder_path()
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "config.toml", "w") as f:
            f.write(textwrap.dedent(text))

        config = sut.Config.load()
        assert config == sut.Config(
            log_level=logging.DEBUG,
            bots=[
                sut.BotConfig(factory="foo:load", pythonpath="./abc"),
                sut.BotConfig(factory="bar", name="bar", config={"one": 1}),
            ],
        )

    def test_load_default(self) -> None:
        config = sut.Config.load()
        assert config.log_level == logging.INFO
