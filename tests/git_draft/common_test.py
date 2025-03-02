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


def test_sql() -> None:
    assert "create" in sut.sql("create-tables")
