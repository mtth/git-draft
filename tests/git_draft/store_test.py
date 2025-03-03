import pytest

import git_draft.store as sut


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
