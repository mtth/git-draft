"""Persistent state storage"""

import contextlib
from datetime import datetime
import functools
import sqlite3
from typing import Iterator, Self

from .common import ensure_state_home, package_root


sqlite3.register_adapter(datetime, lambda d: d.isoformat())
sqlite3.register_converter(
    "timestamp", lambda v: datetime.fromisoformat(v.decode())
)


class Store:
    _name = "v1.sqlite3"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._connection = conn

    @classmethod
    def persistent(cls) -> Self:
        path = ensure_state_home() / cls._name
        conn = sqlite3.connect(str(path), autocommit=False)
        return cls(conn)

    @classmethod
    def in_memory(cls) -> Self:
        return cls(sqlite3.connect(":memory:"))

    @contextlib.contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        with contextlib.closing(self._connection.cursor()) as cursor:
            try:
                yield cursor
            except:  # noqa
                self._connection.rollback()
                raise
            else:
                self._connection.commit()


_query_root = package_root / "queries"


@functools.cache
def sql(name: str) -> str:
    path = _query_root / f"{name}.sql"
    with open(path) as reader:
        return reader.read()
