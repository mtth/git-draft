import logging
from pathlib import Path
import textwrap

import pytest

import git_draft.common as sut


def test_ensure_state_home() -> None:
    path = sut.ensure_state_home()
    assert path.exists()


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
            options = {one=1}
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
                sut.BotConfig(factory="bar", name="bar", options={"one": 1}),
            ],
        )

    def test_load_default(self) -> None:
        config = sut.Config.load()
        assert config.log_level == logging.INFO


class TestConfigString:
    def test_literal(self) -> None:
        assert sut.config_string("") == ""
        assert sut.config_string("abc") == "abc"

    def test_evar(self, monkeypatch) -> None:
        monkeypatch.setenv("FOO", "111")
        assert sut.config_string("$FOO") == "111"


@pytest.mark.parametrize(
    "text,width,prefix,want",
    [
        ("", 10, "", ""),
        ("abc", 5, "", "abc"),
        ("ab", 0, "", "ab"),
        ("\nabc def", 4, "", "abc\ndef"),
        ("  abc\n  def  ", 10, "", "abc def"),
        (
            """
                This is a fun paragraph
                which continues.

                And another.
            """,
            60,
            "",
            "This is a fun paragraph which continues.\n\nAnd another.",
        ),
        (
            """
                A quoted
                something.

                And very long follow up.
            """,
            24,
            ">",
            "> A quoted something.\n>\n> And very long follow\n> up.",
        ),
    ],
)
def test_reindent(text, width, prefix, want):
    assert sut.reindent(text, prefix=prefix, width=width) == want
