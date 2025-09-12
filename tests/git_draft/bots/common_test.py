import pytest

import git_draft.bots.common as sut


class FakeBot(sut.Bot):
    pass


class TestBot:
    def test_state_folder_path(self) -> None:
        assert "bots.common_test.FakeBot" in str(FakeBot.state_folder_path())


class TestActionSummary:
    def test_increment_noinit(self) -> None:
        action = sut.ActionSummary()
        with pytest.raises(ValueError):
            action.increment_request_count()

    def test_increment_request_count(self) -> None:
        action = sut.ActionSummary()
        action.increment_request_count(init=True)
        assert action.request_count == 1
        action.increment_request_count()
        assert action.request_count == 2

    def test_increment_token_count(self) -> None:
        action = sut.ActionSummary()
        action.increment_token_count(5, init=True)
        action.increment_token_count(3)
        assert action.token_count == 8
