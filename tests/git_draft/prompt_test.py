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


class TestTemplate:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self._env = sut._jinja_environment()

    def test_fields(self):
        tpl = sut._Template.create("add-test.jinja", self._env)
        assert not tpl.is_local
        assert tpl.name == "add-test"

    def test_preamble_ok(self):
        tpl = sut._Template.create("add-test.jinja", self._env)
        assert "symbol" in tpl.preamble

    def test_preamble_missing(self):
        tpl = sut._Template.create("includes/.file-list.jinja", self._env)
        assert tpl.preamble is None

    def test_extract_variables(self):
        tpl = sut._Template.create("add-test.jinja", self._env)
        variables = tpl.extract_variables(self._env)
        assert "symbol" in variables
        assert "repo" not in variables
