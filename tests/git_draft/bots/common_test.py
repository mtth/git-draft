import pytest

import git_draft.bots.common as sut


class FakeBot(sut.Bot):
    pass


class TestBot:
    def test_state_folder_path(self) -> None:
        assert "bots.common_test.FakeBot" in str(FakeBot.state_folder_path())


class TestAction:
    def test_increment_request_count_initialization(self) -> None:
        action = sut.Action()
        with pytest.raises(ValueError):
            action.increment_request_count()

    def test_increment_request_count_initial(self) -> None:
        action = sut.Action()
        action.increment_request_count(init=True)
        assert action.request_count == 1
        action.increment_request_count()
        assert action.request_count == 2

    def test_increment_token_count_initialization(self) -> None:
        action = sut.Action()
        with pytest.raises(ValueError):
            action.increment_token_count(5)

    def test_increment_token_count(self, monkeypatch) -> None:
        action = sut.Action()
        action.increment_token_count(5, init=True)
        action.increment_token_count(3)
        assert action.token_count == 8
