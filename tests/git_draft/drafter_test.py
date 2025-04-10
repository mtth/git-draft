from collections.abc import Callable, Mapping, Sequence
import os
from pathlib import Path, PurePosixPath
from typing import Self

import git
import pytest

from git_draft.bots import Action, Bot, Goal, Toolbox
import git_draft.drafter as sut
from git_draft.prompt import TemplatedPrompt
from git_draft.store import Store


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
    def setup(self, repo: git.Repo) -> None:
        self._repo = repo
        self._drafter = sut.Drafter(Store.in_memory(), repo)

    def _path(self, name: str) -> Path:
        return Path(self._repo.working_dir, name)

    def _read(self, name: str) -> str | None:
        try:
            with open(self._path(name)) as f:
                return f.read()
        except FileNotFoundError:
            return None

    def _write(self, name: str, contents="") -> None:
        with open(self._path(name), "w") as f:
            f.write(contents)

    def _delete(self, name: str) -> None:
        os.remove(self._path(name))

    def _commits(self, ref: str | None = None) -> Sequence[git.Commit]:
        return list(self._repo.iter_commits(rev=ref))

    def _commit_files(self, ref: str) -> frozenset[str]:
        text = self._repo.git.diff_tree(
            ref, no_commit_id=True, name_only=True, relative=True
        )
        return frozenset(text.splitlines())

    def _checkout(self) -> None:
        self._repo.git.checkout("--", ".")

    def test_generate_draft(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot({"p1": "A"}))
        assert len(self._commits()) == 2

    def test_generate_empty_draft(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot.noop())
        assert len(self._commits()) == 2

    def test_generate_stages_then_resets_worktree(self) -> None:
        self._write("p1", "a")
        self._write("p2", "b")

        class CustomBot(Bot):
            def act(self, _goal: Goal, toolbox: Toolbox) -> Action:
                assert toolbox.read_file(PurePosixPath("p1")) == "a"
                toolbox.write_file(PurePosixPath("p2"), "B")
                toolbox.write_file(PurePosixPath("p3"), "C")
                return Action()

        self._drafter.generate_draft("hello", CustomBot())
        assert self._commit_files("HEAD") == set(["p2", "p3"])

    def test_generate_outside_branch(self) -> None:
        self._repo.git.checkout("--detach")
        with pytest.raises(RuntimeError):
            self._drafter.generate_draft("ok", _SimpleBot.noop())

    def test_generate_empty_prompt(self) -> None:
        with pytest.raises(ValueError):
            self._drafter.generate_draft("", _SimpleBot.noop())

    def test_generate_dirty_index_no_reset(self) -> None:
        self._write("log")
        self._repo.git.add(all=True)
        with pytest.raises(ValueError):
            self._drafter.generate_draft("hi", _SimpleBot.noop())

    def test_generate_dirty_index_reset_sync(self) -> None:
        self._write("log", "11")
        self._repo.git.add(all=True)
        self._drafter.generate_draft(
            "hi", _SimpleBot.prompt(), reset=True, sync=True
        )
        assert self._read("log") == "11"
        assert not self._path("PROMPT").exists()
        self._repo.git.checkout(".")
        assert self._read("PROMPT") == "hi"
        assert len(self._commits()) == 3  # init, sync, prompt

    def test_generate_clean_index_sync(self) -> None:
        prompt = TemplatedPrompt("add-test", {"symbol": "abc"})
        self._drafter.generate_draft(
            prompt, _SimpleBot({"p1": "abc"}), sync=True
        )
        self._repo.git.checkout(".")
        assert "abc" in (self._read("p1") or "")
        assert len(self._commits()) == 2  # sync, prompt

    def test_generate_reuse_branch(self) -> None:
        bot = _SimpleBot({"prompt": lambda goal: goal.prompt})
        self._drafter.generate_draft("prompt1", bot)
        self._drafter.generate_draft("prompt2", bot)
        self._repo.git.checkout(".")
        assert self._read("prompt") == "prompt2"
        assert len(self._commits()) == 3  # init, prompt, prompt

    def test_generate_reuse_branch_sync(self) -> None:
        bot = _SimpleBot({"p1": "A"})
        self._drafter.generate_draft("prompt1", bot)
        self._drafter.generate_draft("prompt2", bot, sync=True)
        assert len(self._commits()) == 4  # init, prompt, sync, prompt

    def test_generate_noop(self) -> None:
        self._write("unrelated", "a")
        self._drafter.generate_draft("prompt", _SimpleBot.noop())
        assert len(self._commits()) == 2  # init, prompt
        assert not self._commit_files("HEAD")

    def test_generate_accept_checkout(self) -> None:
        self._write("p1", "A")
        self._write("p2", "B")
        self._write("p4", "E")
        self._drafter.generate_draft(
            "hello",
            _SimpleBot({"p1": "C", "p3": "D", "p4": None}),
            accept=sut.Accept.CHECKOUT,
            sync=True,
        )
        assert self._read("p1") == "C"
        assert self._read("p2") == "B"
        assert self._read("p3") == "D"
        assert self._read("p4") is None

    def test_generate_accept_checkout_conflict(self) -> None:
        self._write("p1", "A")
        with pytest.raises(sut.ConflictError):
            self._drafter.generate_draft(
                "hello",
                _SimpleBot({"p1": "B", "p2": "C"}),
                accept=sut.Accept.CHECKOUT
            )
        assert """<<<<<<< ours\nA""" in (self._read("p1") or "")
        assert self._read("p2") == "C"

    def test_generate_accept_finalize(self) -> None:
        self._write("p1", "A")
        self._drafter.generate_draft(
            "hello",
            _SimpleBot({"p2": "B"}),
            accept=sut.Accept.FINALIZE,
        )
        assert self._read("p1") == "A"
        assert self._read("p2") == "B"
        assert self._repo.active_branch.name == "main"

    def test_delete_unknown_file(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot({"p1": None}))

    def test_finalize_keeps_changes(self) -> None:
        self._write("p1.txt", "a1")
        self._drafter.generate_draft("hello", _SimpleBot.prompt())
        self._checkout()
        self._write("p1.txt", "a2")
        self._drafter.finalize_draft()
        assert self._read("p1.txt") == "a2"
        assert self._read("PROMPT") == "hello"

    def test_finalize_and_sync(self) -> None:
        draft = self._drafter.generate_draft(
            "hello",
            _SimpleBot.prompt(),
            accept=sut.Accept.CHECKOUT,
        )
        self._write("PROMPT", "a2")
        self._drafter.finalize_draft(sync=True)
        assert self._read("PROMPT") == "a2"
        commits = self._commits(draft.branch_name)
        assert len(commits) == 3  # init, prompt, sync
        assert "sync" in commits[0].message

    def test_history_table_empty(self) -> None:
        table = self._drafter.history_table()
        assert not table

    def test_history_table_active_draft(self) -> None:
        self._drafter.generate_draft("hello", _SimpleBot.noop())
        table = self._drafter.history_table()
        assert table

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
