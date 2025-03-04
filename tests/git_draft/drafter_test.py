import git
import os.path as osp
from pathlib import PurePosixPath
import pytest

from git_draft.bots import Action, Bot, Toolbox
import git_draft.drafter as sut
from git_draft.store import Store


class _FakeBot(Bot):
    def act(self, prompt: str, toolbox: Toolbox) -> Action:
        toolbox.write_file(PurePosixPath("PROMPT"), prompt)
        return Action()


@pytest.fixture
def drafter(repo: git.Repo) -> sut.Drafter:
    return sut.Drafter(Store.in_memory(), repo)


class TestDrafter:
    def test_generate_draft(
        self, drafter: sut.Drafter, repo: git.Repo
    ) -> None:
        drafter.generate_draft("hello", _FakeBot())
        commits = list(repo.iter_commits())
        assert len(commits) == 2

    def test_generate_then_discard_draft(
        self, drafter: sut.Drafter, repo: git.Repo
    ) -> None:
        drafter.generate_draft("hello", _FakeBot())
        drafter.discard_draft()
        assert len(list(repo.iter_commits())) == 1

    def test_discard_restores_worktree(
        self, drafter: sut.Drafter, repo: git.Repo
    ) -> None:
        p1 = osp.join(repo.working_dir, "p1.txt")
        with open(p1, "w") as writer:
            writer.write("a1")
        p2 = osp.join(repo.working_dir, "p2.txt")
        with open(p2, "w") as writer:
            writer.write("b1")

        drafter.generate_draft("hello", _FakeBot(), sync=True)
        with open(p1, "w") as writer:
            writer.write("a2")

        drafter.discard_draft()

        with open(p1) as reader:
            assert reader.read() == "a1"
        with open(p2) as reader:
            assert reader.read() == "b1"

    def test_finalize_keeps_changes(
        self, drafter: sut.Drafter, repo: git.Repo
    ) -> None:
        p1 = osp.join(repo.working_dir, "p1.txt")
        with open(p1, "w") as writer:
            writer.write("a1")

        drafter.generate_draft("hello", _FakeBot(), checkout=True)
        with open(p1, "w") as writer:
            writer.write("a2")

        drafter.finalize_draft()

        with open(p1) as reader:
            assert reader.read() == "a2"
        with open(osp.join(repo.working_dir, "PROMPT")) as reader:
            assert reader.read() == "hello"
