import shutil

import git_draft.editor as sut


class TestGuessEditorBinPath:
    def test_from_env_ok(self, monkeypatch) -> None:
        def which(editor):
            assert editor == "foo"
            return "/bin/bar"

        monkeypatch.setattr(shutil, "which", which)
        monkeypatch.setenv("EDITOR", "foo")

        assert sut._guess_editor_binpath() == "/bin/bar"

    def test_from_env_missing(self, monkeypatch) -> None:
        def which(_editor):
            return ""

        monkeypatch.setattr(shutil, "which", which)
        monkeypatch.setenv("EDITOR", "foo")

        assert sut._guess_editor_binpath() == ""

    def test_from_default_ok(self, monkeypatch) -> None:
        def which(editor):
            return "/bin/nano" if editor == "nano" else ""

        monkeypatch.setattr(shutil, "which", which)
        monkeypatch.setenv("EDITOR", "")

        assert sut._guess_editor_binpath() == "/bin/nano"

    def test_from_default_missing(self, monkeypatch) -> None:
        def which(_editor):
            return ""

        monkeypatch.setattr(shutil, "which", which)
        monkeypatch.setenv("EDITOR", "")

        assert sut._guess_editor_binpath() == ""
