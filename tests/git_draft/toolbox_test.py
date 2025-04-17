from pathlib import Path, PurePosixPath

import pytest

from git_draft.git import GitError, Repo
import git_draft.toolbox as sut


class TestStagingToolbox:
    @pytest.fixture(autouse=True)
    def setup(self, repo: Repo) -> None:
        self._toolbox = sut.StagingToolbox(repo)

    def test_list_files(self, repo: Repo) -> None:
        assert self._toolbox.list_files() == []
        names = set(["one.txt", "two.txt"])
        for name in names:
            with Path(repo.working_dir, name).open("w") as f:
                f.write("ok")
        repo.git("add", "--all")
        assert set(str(p) for p in self._toolbox.list_files()) == names

    def test_read_file(self, repo: Repo) -> None:
        with Path(repo.working_dir, "one").open("w") as f:
            f.write("ok")

        path = PurePosixPath("one")
        with pytest.raises(GitError):
            self._toolbox.read_file(path)

        repo.git("add", "--all")
        assert self._toolbox.read_file(path) == "ok"

    def test_write_file(self, repo: Repo) -> None:
        self._toolbox.write_file(PurePosixPath("one"), "hi")

        path = Path(repo.working_dir, "one")
        assert not path.exists()

        repo.git("checkout-index", "--all")
        with path.open() as f:
            assert f.read() == "hi"

    def test_rename_file(self, repo: Repo) -> None:
        self._toolbox.write_file(PurePosixPath("one"), "hi")
        self._toolbox.rename_file(PurePosixPath("one"), PurePosixPath("two"))

        repo.git("checkout-index", "--all")
        assert not Path(repo.working_dir, "one").exists()
        with Path(repo.working_dir, "two").open() as f:
            assert f.read() == "hi"
