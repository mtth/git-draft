from pathlib import PurePosixPath

import pytest

from git_draft.git import Repo
import git_draft.toolbox as sut

from .conftest import RepoFS


PPP = PurePosixPath


class TestRepoToolbox:
    @pytest.fixture(autouse=True)
    def setup(self, repo: Repo, repo_fs: RepoFS) -> None:
        self._repo = repo
        self._fs = repo_fs

    def test_list_files(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.flush()

        toolbox = sut.RepoToolbox(self._repo, "HEAD")
        self._fs.delete("f2")
        self._fs.write("f3", "c")
        assert set(str(p) for p in toolbox.list_files()) == {"f1", "f2"}

    def test_read_file(self) -> None:
        self._fs.write("f1", "a")
        sha = self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.flush()
        self._fs.write("f2", "b")

        toolbox = sut.RepoToolbox(self._repo, sha)
        assert toolbox.read_file(PPP("f1")) == "a"
        assert toolbox.read_file(PPP("f2")) is None
        assert toolbox.read_file(PPP("f3")) is None

    def test_write_file(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        sha = self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.flush()

        toolbox = sut.RepoToolbox(self._repo, sha)
        toolbox.write_file(PPP("f1"), "aaa")
        toolbox.write_file(PPP("f3"), "c")
        assert toolbox.read_file(PPP("f1")) == "aaa"
        assert toolbox.read_file(PPP("f3")) == "c"
        assert self._fs.read("f1") == "aa"
        assert self._fs.read("f3") is None

    def test_for_working_dir_dirty(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.write("f3", "c")
        self._fs.flush()
        self._fs.write("f1", "aa")
        self._fs.delete("f2")

        toolbox, dirty = sut.RepoToolbox.for_working_dir(self._repo)
        assert dirty
        assert toolbox.read_file(PPP("f1")) == "aa"
        assert toolbox.read_file(PPP("f2")) is None
        assert toolbox.read_file(PPP("f3")) == "c"

    def test_expose_files(self) -> None:
        self._fs.write("f1", "a")
        self._fs.write("f2", "b")
        self._fs.flush()
        toolbox = sut.RepoToolbox(self._repo, "HEAD")
        toolbox.delete_file(PPP("f1"))
        toolbox.write_file(PPP("f3"), "c")

        with toolbox.expose_files() as path:
            assert {".git", "f2", "f3"} == set(c.name for c in path.iterdir())
            with open(path / "f2", "w") as w:
                w.write("bb")
            with open(path / "f4", "w") as w:
                w.write("d")
            (path / "f3").unlink()

            # Before sync, toolbox does not have changes.
            assert toolbox.read_file(PPP("f2")) == "b"
            assert toolbox.read_file(PPP("f3")) == "c"

        # After sync, toolbox has changes propagated.
        assert toolbox.read_file(PPP("f2")) == "bb"
        assert toolbox.read_file(PPP("f3")) is None
        assert toolbox.read_file(PPP("f4")) == "d"
