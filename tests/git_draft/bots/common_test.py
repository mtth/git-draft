from pathlib import PurePosixPath
import pytest
import unittest.mock

import git_draft.bots.common as sut


class FakeToolbox(sut.Toolbox):
    def _list(self):
        return [PurePosixPath("/mock/path")]

    def _read(self, path: PurePosixPath) -> str:
        return "file contents"

    def _write(self, path: PurePosixPath, contents: str) -> None:
        pass

    def _delete(self, path: PurePosixPath) -> None:
        pass


class TestToolbox:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self._hook = unittest.mock.MagicMock()
        self._toolbox = FakeToolbox(hook=self._hook)

    def test_list_files(self):
        result = self._toolbox.list_files()
        assert result == [PurePosixPath("/mock/path")]
        self._hook.assert_called_once()
        assert self._toolbox.operations[0].tool == "list_files"

    def test_read_file(self):
        content = self._toolbox.read_file(PurePosixPath("/mock/path"))
        assert content == "file contents"
        self._hook.assert_called_once()
        assert self._toolbox.operations[0].tool == "read_file"

    def test_write_file(self):
        self._toolbox.write_file(PurePosixPath("/mock/path"), "new contents")
        self._hook.assert_called_once()
        assert self._toolbox.operations[0].tool == "write_file"

    def test_delete_file(self):
        self._toolbox.delete_file(PurePosixPath("/mock/path"))
        self._hook.assert_called_once()
        assert self._toolbox.operations[0].tool == "delete_file"


class FakeBot(sut.Bot):
    pass


class TestBot:
    def test_state_folder_path(self) -> None:
        assert "bots.common_test.FakeBot" in str(FakeBot.state_folder_path())
