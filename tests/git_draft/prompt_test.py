import pytest

import git_draft.prompt as sut
from git_draft.worktrees import GitWorktree


class TestCheckPublicTemplateName:
    @pytest.mark.parametrize("name", ["ok", ".hidden", "composite-name"])
    def test_ok(self, name: str) -> None:
        sut._check_public_template_name(name)

    @pytest.mark.parametrize("name", ["", "ABC", ".PROMPT", ".with.ext"])
    def test_raises(self, name: str) -> None:
        with pytest.raises(ValueError):
            sut._check_public_template_name(name)


class TestTemplatedPrompt:
    @pytest.fixture(autouse=True)
    def setup(self, repo) -> None:
        self._tree = GitWorktree(repo, "HEAD")

    def test_ok(self) -> None:
        prompt = sut.TemplatedPrompt("add-test", ("--symbol=foo",))
        rendered = prompt.render(self._tree)
        assert "foo" in rendered

    def test_missing_variable(self) -> None:
        prompt = sut.TemplatedPrompt("add-test")
        with pytest.raises(ValueError):
            prompt.render(self._tree)


class TestFindPromptMetadata:
    def test_ok(self) -> None:
        metadata = sut.find_prompt_metadata("add-test")
        assert metadata
        assert "symbol" in (metadata.description or "")

    def test_missing(self) -> None:
        assert sut.find_prompt_metadata("foo") is None


def test_templates_table() -> None:
    assert sut.templates_table(include_local=False)
