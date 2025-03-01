import dataclasses
import git
from pathlib import PurePosixPath
import pytest
import tempfile
from typing import Iterator

from git_draft.assistant import Assistant, Session, Toolbox
import git_draft.manager as sut


@pytest.fixture
def repo() -> Iterator[git.Repo]:
    with tempfile.TemporaryDirectory() as name:
        repo = git.Repo.init(name)
        repo.index.commit("init")
        yield repo


@dataclasses.dataclass(frozen=True)
class _FakeNote(sut._Note, name="draft-test"):
    value: int


class TestNote:
    def test_write_one(self, repo: git.Repo) -> None:
        note = _FakeNote(2)
        note.write(repo, "main")
        data = repo.git.notes("show", "main")
        assert data == 'draft-test: {"value":2}'

    def test_write_read_one(self, repo: git.Repo) -> None:
        note = _FakeNote(1)
        note.write(repo, "main")
        assert note == _FakeNote.read(repo, "main")

    def test_write_multiple(self, repo: git.Repo) -> None:
        _FakeNote(1).write(repo, "main")
        _FakeNote(2).write(repo, "main")
        data = repo.git.notes("show", "main")
        assert data == "\n".join(
            [
                'draft-test: {"value":1}',
                'draft-test: {"value":2}',
            ]
        )


class _FakeAssistant(Assistant):
    def run(self, prompt: str, toolbox: Toolbox) -> Session:
        toolbox.write_file(PurePosixPath("PROMPT"), prompt)
        return Session(len(prompt), [])


class TestManager:
    def test_generate_draft(self, repo: git.Repo) -> None:
        manager = sut.Manager(repo)
        manager.generate_draft("hello", _FakeAssistant())
        commits = list(repo.iter_commits())
        assert len(commits) == 3

    def test_generate_then_discard_draft(self, repo: git.Repo) -> None:
        manager = sut.Manager(repo)
        manager.generate_draft("hello", _FakeAssistant())
        manager.discard_draft()
        assert len(list(repo.iter_commits())) == 1
