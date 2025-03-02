import pytest
import tempfile
from typing import Iterator

import git_draft.common as sut


@pytest.fixture(autouse=True)
def state_home(monkeypatch) -> Iterator[str]:
    with tempfile.TemporaryDirectory() as name:
        monkeypatch.setenv("XDG_STATE_HOME", name)
        yield name


def test_ensure_state_home(state_home) -> None:
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
