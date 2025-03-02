import logging
from pathlib import Path
import pytest
import textwrap

import git_draft.common as sut


@pytest.fixture(autouse=True)
def state_home(monkeypatch, tmp_path) -> None:
    path = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(path))


def test_ensure_state_home() -> None:
    path = sut._ensure_state_home()
    assert path.exists()


class TestStore:
    def test_cursor(self) -> None:
        store = sut.Store.persistent()
        with store.cursor() as cursor:
            cursor.execute("create table foo(id int)")
            cursor.execute("insert into foo values (1), (2)")
        with store.cursor() as cursor:
            data = cursor.execute("select * from foo")
            assert list(data) == [(1,), (2,)]


class TestSQL:
    def test_ok(self) -> None:
        assert "create" in sut.sql("create-tables")

    def test_missing(self) -> None:
        with pytest.raises(FileNotFoundError):
            sut.sql("non_existent_file")


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

            [bots.foo]
            loader = "foo:load"
            pythonpath = "./abc"

            [bots.bar]
            loader = "bar"
            kwargs = {one=1}
        """
        path = sut.Config.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(textwrap.dedent(text))

        config = sut.Config.load()
        assert config == sut.Config(
            log_level=logging.DEBUG,
            bots={
                "foo": sut.BotConfig(loader="foo:load", pythonpath="./abc"),
                "bar": sut.BotConfig(loader="bar", kwargs={"one": 1}),
            },
        )

    def test_load_default(self) -> None:
        config = sut.Config.load()
        assert config.log_level == logging.INFO
