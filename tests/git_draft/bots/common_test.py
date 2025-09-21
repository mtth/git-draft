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
            action.increment_turn_count()

    def test_increment_turn_count(self) -> None:
        action = sut.ActionSummary()
        action.increment_turn_count(init=True)
        assert action.turn_count == 1
        action.increment_turn_count()
        assert action.turn_count == 2

    def test_increment_token_count(self) -> None:
        action = sut.ActionSummary()
        action.increment_token_count(5, init=True)
        action.increment_token_count(3)
        assert action.token_count == 8
