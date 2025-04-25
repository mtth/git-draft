from collections.abc import Callable, Mapping, Sequence
from pathlib import PurePosixPath
from typing import Self

import pytest

from git_draft.bots import Action, Bot, Goal, Toolbox
from git_draft.common import Feedback
import git_draft.drafter as sut
from git_draft.git import SHA, GitError, Repo
from git_draft.store import Store

from .conftest import RepoFS


class _SimpleBot(Bot):
    """A simple bot which updates files to match a mapping"""

    def __init__(
        self, contents: Mapping[str, str | None | Callable[[Goal], str]]
    ) -> None:
        self._contents = contents

    @classmethod
    def noop(cls) -> Self:
        return cls({})

    @classmethod
    def prompt(cls) -> Self:
        return cls({"PROMPT": lambda goal: goal.prompt})

    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        for key, value in self._contents.items():
            path = PurePosixPath(key)
            if value is None:
                toolbox.delete_file(path)
            else:
                contents = value if isinstance(value, str) else value(goal)
                toolbox.write_file(path, contents)
        return Action()


class TestDrafter:
    @pytest.fixture(autouse=True)
    def setup(self, repo: Repo, repo_fs: RepoFS) -> None:
        self._repo = repo
        self._fs = repo_fs
        self._drafter = sut.Drafter.create(
            repo, Store.in_memory(), Feedback.static()
        )

    def _commits(self, ref: str | None = None) -> Sequence[SHA]:
        git = self._repo.git("log", "--pretty=format:%H", ref or "HEAD")
        return git.stdout.splitlines()

    def _commit_files(self, ref: str) -> frozenset[str]:
        git = self._repo.git(
            "diff-tree", ref, "--no-commit-id", "--name-only", "--relative"
        )
        return frozenset(git.stdout.splitlines())

    def _checkout(self) -> None:
        self._repo.git("checkout", "--", ".")

    def test_generate_draft(self) -> None:
        self._fs.write("p1", "a")
        self._drafter.generate_draft("hello", _SimpleBot({"p1": "A"}))
        assert len(self._commits()) == 1
        assert len(self._commits("@{u}")) == 3
        assert self._fs.read("p1") == "a"

    def test_generate_empty_draft(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot.noop())
        assert len(self._commits()) == 1
        assert len(self._commits("@{u}")) == 2

    def test_generate_draft_merge(self) -> None:
        self._fs.write("p1", "a")

        self._drafter.generate_draft(
            "hello", _SimpleBot({"p2": "b"}), merge_strategy="ignore-all-space"
        )
        # No sync(merge) commit since no changes happened between.
        assert len(self._commits()) == 4  # init, sync(prompt), prompt, merge
        assert self._fs.read("p1") == "a"
        assert self._fs.read("p2") == "b"

    def test_generate_draft_merge_no_conflict(self) -> None:
        self._fs.write("p1", "a")

        def update(_goal: Goal) -> str:
            self._fs.write("p2", "b")
            return "A"

        self._drafter.generate_draft(
            "hello",
            _SimpleBot({"p1": update}),
            merge_strategy="ignore-all-space",
        )
        assert len(self._commits()) == 5  # init, sync, prompt, sync, merge
        assert self._fs.read("p1") == "A"
        assert self._fs.read("p2") == "b"

    def test_generate_draft_merge_theirs(self) -> None:
        self._fs.write("p1", "a")

        def update(_goal: Goal) -> str:
            self._fs.write("p1", "b")
            return "A"

        self._drafter.generate_draft(
            "hello", _SimpleBot({"p1": update}), merge_strategy="theirs"
        )
        # sync(merge) commit here since p1 was updated separately.
        assert len(self._commits()) == 5  # init, sync, prompt, sync, merge
        assert self._fs.read("p1") == "A"

    def test_generate_draft_merge_conflict(self) -> None:
        self._fs.write("p1", "a")

        def update(_goal: Goal) -> str:
            self._fs.write("p1", "b")
            return "A"

        with pytest.raises(GitError):
            self._drafter.generate_draft(
                "hello",
                _SimpleBot({"p1": update}),
                merge_strategy="ignore-all-space",
            )

    def test_generate_outside_branch(self) -> None:
        self._repo.git("checkout", "--detach")
        with pytest.raises(RuntimeError):
            self._drafter.generate_draft("ok", _SimpleBot.noop())

    def test_generate_empty_prompt(self) -> None:
        with pytest.raises(ValueError):
            self._drafter.generate_draft("", _SimpleBot.noop())

    def test_generate_reuse_branch(self) -> None:
        bot = _SimpleBot({"prompt": lambda goal: goal.prompt})
        self._drafter.generate_draft("prompt1", bot, "theirs")
        self._drafter.generate_draft("prompt2", bot, "theirs")
        assert self._fs.read("prompt") == "prompt2"

    def test_delete_unknown_file(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot({"p1": None}))

    def test_quit_keeps_changes(self) -> None:
        self._fs.write("p1.txt", "a1")
        self._drafter.generate_draft("hello", _SimpleBot.prompt(), "theirs")
        self._fs.write("p1.txt", "a2")
        self._drafter.quit_folio()
        assert self._fs.read("p1.txt") == "a2"
        assert self._fs.read("PROMPT") == "hello"

    def test_latest_draft_prompt(self) -> None:
        bot = _SimpleBot.noop()

        prompt1 = "First prompt"
        self._drafter.generate_draft(prompt1, bot)
        assert self._drafter.latest_draft_prompt() == prompt1

        prompt2 = "Second prompt"
        self._drafter.generate_draft(prompt2, bot)
        assert self._drafter.latest_draft_prompt() == prompt2

    def test_latest_draft_prompt_no_active_branch(self) -> None:
        assert self._drafter.latest_draft_prompt() is None
