import git
import os.path as osp
from pathlib import PurePosixPath
import pytest

from git_draft.bots import Action, Bot, Toolbox
from git_draft.common import Store
import git_draft.manager as sut


class _FakeBot(Bot):
    def act(self, prompt: str, toolbox: Toolbox) -> Action:
        toolbox.write_file(PurePosixPath("PROMPT"), prompt)
        return Action()


@pytest.fixture
def manager(repo: git.Repo) -> sut.Manager:
    return sut.Manager(Store.in_memory(), repo)


class TestManager:
    def test_generate_draft(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        manager.generate_draft("hello", _FakeBot())
        commits = list(repo.iter_commits())
        assert len(commits) == 2

    def test_generate_then_discard_draft(
        self, manager: sut.Manager, repo: git.Repo
    ) -> None:
        manager.generate_draft("hello", _FakeBot())
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

        manager.generate_draft("hello", _FakeBot(), sync=True)
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

        manager.generate_draft("hello", _FakeBot(), checkout=True)
        with open(p1, "w") as writer:
            writer.write("a2")

        manager.finalize_draft()

        with open(p1) as reader:
            assert reader.read() == "a2"
        with open(osp.join(repo.working_dir, "PROMPT")) as reader:
            assert reader.read() == "hello"
