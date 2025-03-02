import git
import os.path as osp
from pathlib import PurePosixPath
import pytest
import tempfile
from typing import Iterator

from git_draft.assistants import Assistant, Session, Toolbox
from git_draft.common import Store
import git_draft.manager as sut


@pytest.fixture
def repo() -> Iterator[git.Repo]:
    with tempfile.TemporaryDirectory() as name:
        repo = git.Repo.init(name, initial_branch="main")
        repo.index.commit("init")
        yield repo


class _FakeAssistant(Assistant):
    def run(self, prompt: str, toolbox: Toolbox) -> Session:
        toolbox.write_file(PurePosixPath("PROMPT"), prompt)
        return Session(len(prompt))


@pytest.fixture
def manager(repo: git.Repo) -> sut.Manager:
    return sut.Manager(Store.in_memory(), repo)


class TestManager:
    def test_generate_draft(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        manager.generate_draft("hello", _FakeAssistant())
        commits = list(repo.iter_commits())
        assert len(commits) == 2

    def test_generate_then_discard_draft(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        manager.generate_draft("hello", _FakeAssistant())
        manager.discard_draft()
        assert len(list(repo.iter_commits())) == 1

    def test_discard_restores_worktree(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        p1 = osp.join(repo.working_dir, "p1.txt")
        with open(p1, "w") as writer:
            writer.write("a1")
        p2 = osp.join(repo.working_dir, "p2.txt")
        with open(p2, "w") as writer:
            writer.write("b1")

        manager.generate_draft("hello", _FakeAssistant(), sync=True)
        with open(p1, "w") as writer:
            writer.write("a2")

        manager.discard_draft()

        with open(p1) as reader:
            assert reader.read() == "a1"
        with open(p2) as reader:
            assert reader.read() == "b1"

    def test_finalize_keeps_changes(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        p1 = osp.join(repo.working_dir, "p1.txt")
        with open(p1, "w") as writer:
            writer.write("a1")

        manager.generate_draft("hello", _FakeAssistant(), checkout=True)
        with open(p1, "w") as writer:
            writer.write("a2")

        manager.finalize_draft()

        with open(p1) as reader:
            assert reader.read() == "a2"
        with open(osp.join(repo.working_dir, "PROMPT")) as reader:
            assert reader.read() == "hello"
