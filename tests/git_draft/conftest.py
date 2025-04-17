from collections.abc import Iterator
from pathlib import Path

import pytest

from git_draft.git import Git, Repo


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    path = tmp_path / "repo"
    path.mkdir()
    Git.run("-C", str(path), "init", "-b", "main")
    repo = Repo.enclosing(path)
    repo.git("commit", "-m", "init", "--allow-empty")
    yield repo


@pytest.fixture(autouse=True)
def state_home(monkeypatch, tmp_path) -> None:
    path = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(path))
