from pathlib import Path, PurePosixPath

import git
import pytest

import git_draft.toolbox as sut


class TestStagingToolbox:
    @pytest.fixture(autouse=True)
    def setup(self, repo: git.Repo) -> None:
        self._toolbox = sut.StagingToolbox(repo)

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
