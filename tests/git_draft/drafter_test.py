import git
import os.path as osp
from pathlib import Path, PurePosixPath
import pytest

from git_draft.bots import Action, Bot, Toolbox
import git_draft.drafter as sut
from git_draft.store import Store


class TestToolbox:
    @pytest.fixture(autouse=True)
    def setup(self, repo: git.Repo) -> None:
        self._toolbox = sut._Toolbox(repo, None)

    def test_list_files(self, repo: git.Repo) -> None:
        assert self._toolbox.list_files() == []
        names = set(["one.txt", "two.txt"])
        for name in names:
            with open(Path(repo.working_dir, name), "w") as f:
                f.write("ok")
        repo.git.add(all=True)
        assert set(self._toolbox.list_files()) == names

    def test_read_file(self, repo: git.Repo) -> None:
        with open(Path(repo.working_dir, "one"), "w") as f:
            f.write("ok")

        path = PurePosixPath("one")
        with pytest.raises(git.GitCommandError):
            assert self._toolbox.read_file(path) == ""

        repo.git.add(all=True)
        assert self._toolbox.read_file(path) == "ok"

    def test_write_file(self, repo: git.Repo) -> None:
        self._toolbox.write_file(PurePosixPath("one"), "hi")

        path = Path(repo.working_dir, "one")
        assert not path.exists()

        repo.git.checkout_index(all=True)
        with open(path) as f:
            assert f.read() == "hi"


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
