from pathlib import Path
from typing import Iterator
import git
import pytest


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[git.Repo]:
    repo = git.Repo.init(str(tmp_path / "repo"), initial_branch="main")
    repo.index.commit("init")
    yield repo
