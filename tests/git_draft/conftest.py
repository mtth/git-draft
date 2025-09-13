from collections.abc import Iterator
import os
from pathlib import Path

import pytest

from git_draft.git import GitCall, Repo


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repo]:
    path = tmp_path / "repo"
    path.mkdir()
    GitCall.sync("init", "-b", "main", working_dir=path)
    repo = Repo.enclosing(path)
    repo.git("commit", "-m", "init", "--allow-empty")
    yield repo


@pytest.fixture(autouse=True)
def state_home(monkeypatch, tmp_path) -> None:
    path = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(path))


class RepoFS:
    def __init__(self, repo: Repo) -> None:
        self._repo = repo

    def path(self, name: str) -> Path:
        return Path(self._repo.working_dir, name)

    def read(self, name: str) -> str | None:
        try:
            with open(self.path(name)) as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write(self, name: str, contents="") -> None:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(contents)

    def delete(self, name: str) -> None:
        os.remove(self.path(name))

    def flush(self, message: str = "flush") -> str:
        self._repo.git("add", "-A")
        self._repo.git("commit", "--allow-empty", "-m", message)
        return self._repo.git("rev-parse", "HEAD").stdout


@pytest.fixture
def repo_fs(repo: Repo) -> RepoFS:
    return RepoFS(repo)
