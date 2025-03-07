import git_draft.bots.common as sut


class FakeBot(sut.Bot):
    pass


class TestBot:
    def test_state_folder_path(self) -> None:
        assert "bots.common_test.FakeBot" in str(FakeBot.state_folder_path())
