import pytest

import git_draft.prompt as sut


class TestPromptRenderer:
    @pytest.fixture(autouse=True)
    def setup(self, repo) -> None:
        self._renderer = sut.PromptRenderer.for_repo(repo)

    def test_ok(self) -> None:
        prompt = sut.TemplatedPrompt.parse("add-test", "symbol=foo")
        rendered = self._renderer.render(prompt)
        assert "foo" in rendered
