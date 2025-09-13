from pathlib import PurePosixPath

import pytest

from git_draft.git import Repo
import git_draft.worktrees as sut

from .conftest import RepoFS


PPP = PurePosixPath


class TestRepoWorktree:
    @pytest.fixture(autouse=True)
    def setup(self, repo: Repo, repo_fs: RepoFS) -> None:
        self._repo = repo
        self._fs = repo_fs

    def test_list_files(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.flush()

        tree = sut.GitWorktree(self._repo, "HEAD")
        self._fs.delete("f2")
        self._fs.write("f3", "c")
        assert set(str(p) for p in tree.list_files()) == {"f1", "f2"}

    def test_read_file(self) -> None:
        self._fs.write("f1", "a")
        sha = self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.flush()
        self._fs.write("f2", "b")

        tree = sut.GitWorktree(self._repo, sha)
        assert tree.read_file(PPP("f1")) == "a"
        assert tree.read_file(PPP("f2")) is None
        assert tree.read_file(PPP("f3")) is None

    def test_write_file(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        sha = self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.flush()

        tree = sut.GitWorktree(self._repo, sha)
        tree.write_file(PPP("f1"), "aaa")
        tree.write_file(PPP("f3"), "c")
        assert tree.read_file(PPP("f1")) == "aaa"
        assert tree.read_file(PPP("f3")) == "c"
        assert self._fs.read("f1") == "aa"
        assert self._fs.read("f3") is None

    def test_write_file_in_new_folder(self) -> None:
        self._fs.write("d1/f1", "a")
        sha = self._fs.flush()

        tree = sut.GitWorktree(self._repo, sha)
        tree.write_file(PPP("d1/f2"), "b")  # In existing directory
        tree.write_file(PPP("d1/d2/f3"), "c")  # In new directory
        assert tree.read_file(PPP("d1/f2")) == "b"
        assert tree.read_file(PPP("d1/d2/f3")) == "c"

    def test_for_working_dir_dirty(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.write("f3", "c")
        self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.delete("f2")

        tree, dirty = sut.GitWorktree.for_working_dir(self._repo)
        assert dirty
        assert tree.read_file(PPP("f1")) == "aa"
        assert tree.read_file(PPP("f2")) is None
        assert tree.read_file(PPP("f3")) == "c"

    def test_edit_files(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.flush()
        tree = sut.GitWorktree(self._repo, "HEAD")
        tree.delete_file(PPP("f1"))
        tree.write_file(PPP("f3"), "c")

        with tree.edit_files() as path:
            assert {".git", "f2", "f3"} == set(c.name for c in path.iterdir())
            with open(path / "f2", "w") as w:
                w.write("bb")
            with open(path / "f4", "w") as w:
                w.write("d")
            (path / "f3").unlink()

            # Before sync, tree does not have changes.
            assert tree.read_file(PPP("f2")) == "b"
            assert tree.read_file(PPP("f3")) == "c"

        # After sync, tree has changes propagated.
        assert tree.read_file(PPP("f2")) == "bb"
        assert tree.read_file(PPP("f3")) is None
        assert tree.read_file(PPP("f4")) == "d"
