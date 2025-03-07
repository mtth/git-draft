import pytest

import git_draft.prompt as sut
from git_draft.toolbox import StagingToolbox


class TestPromptRenderer:
    @pytest.fixture(autouse=True)
    def setup(self, repo) -> None:
        toolbox = StagingToolbox(repo)
        self._renderer = sut.PromptRenderer.for_toolbox(toolbox)

    def test_ok(self) -> None:
        prompt = sut.TemplatedPrompt.parse("add-test", "symbol=foo")
        rendered = self._renderer.render(prompt)
        assert "foo" in rendered
