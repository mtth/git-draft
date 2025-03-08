import os
from pathlib import Path, PurePosixPath
from typing import Sequence

import git
import pytest

from git_draft.bots import Action, Bot, Goal, Toolbox
import git_draft.drafter as sut
from git_draft.prompt import TemplatedPrompt
from git_draft.store import Store


class FakeBot(Bot):
    def act(self, goal: Goal, toolbox: Toolbox) -> Action:
        toolbox.write_file(PurePosixPath("PROMPT"), goal.prompt)
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

    def _commits(self) -> Sequence[git.Commit]:
        return list(self._repo.iter_commits())

    def _commit_files(self, ref: str) -> frozenset[str]:
        text = self._repo.git.diff_tree(
            ref, no_commit_id=True, name_only=True, relative=True
        )
        return frozenset(text.splitlines())

    def _checkout(self) -> None:
        self._repo.git.checkout("--", ".")

    def test_generate_draft(self) -> None:
        self._drafter.generate_draft("hello", FakeBot())
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

    def test_generate_then_revert_draft(self) -> None:
        self._drafter.generate_draft("hello", FakeBot())
        self._drafter.revert_draft()
        assert len(self._commits()) == 1

    def test_generate_outside_branch(self) -> None:
        self._repo.git.checkout("--detach")
        with pytest.raises(RuntimeError):
            self._drafter.generate_draft("ok", FakeBot())

    def test_generate_empty_prompt(self) -> None:
        with pytest.raises(ValueError):
            self._drafter.generate_draft("", FakeBot())

    def test_generate_dirty_index_no_reset(self) -> None:
        self._write("log")
        self._repo.git.add(all=True)
        with pytest.raises(ValueError):
            self._drafter.generate_draft("hi", FakeBot())

    def test_generate_dirty_index_reset_sync(self) -> None:
        self._write("log", "11")
        self._repo.git.add(all=True)
        self._drafter.generate_draft("hi", FakeBot(), reset=True, sync=True)
        assert self._read("log") == "11"
        assert not self._path("PROMPT").exists()
        self._repo.git.checkout(".")
        assert self._read("PROMPT") == "hi"
        assert len(self._commits()) == 3  # init, sync, prompt

    def test_generate_clean_index_sync(self) -> None:
        prompt = TemplatedPrompt("add-test", {"symbol": "abc"})
        self._drafter.generate_draft(prompt, FakeBot(), sync=True)
        self._repo.git.checkout(".")
        assert "abc" in (self._read("PROMPT") or "")
        assert len(self._commits()) == 2  # init, prompt

    def test_generate_reuse_branch(self) -> None:
        bot = FakeBot()
        self._drafter.generate_draft("prompt1", bot)
        self._drafter.generate_draft("prompt2", bot)
        self._repo.git.checkout(".")
        assert self._read("PROMPT") == "prompt2"
        assert len(self._commits()) == 3  # init, prompt, prompt

    def test_generate_reuse_branch_sync(self) -> None:
        bot = FakeBot()
        self._drafter.generate_draft("prompt1", bot)
        self._drafter.generate_draft("prompt2", bot, sync=True)
        assert len(self._commits()) == 4  # init, prompt, sync, prompt

    def test_generate_noop(self) -> None:
        self._write("unrelated", "a")

        class CustomBot(Bot):
            def act(self, _goal: Goal, _toolbox: Toolbox) -> Action:
                return Action()

        self._drafter.generate_draft("prompt", CustomBot())
        assert len(self._commits()) == 2  # init, prompt
        assert not self._commit_files("HEAD")

    def test_delete_unknown_file(self) -> None:
        class CustomBot(Bot):
            def act(self, _goal: Goal, toolbox: Toolbox) -> Action:
                toolbox.delete_file(PurePosixPath("p1"))
                return Action()

        self._drafter.generate_draft("hello", CustomBot())

    def test_sync_delete(self) -> None:
        self._write("p1", "a")
        self._repo.git.add(all=True)
        self._repo.index.commit("advance")
        self._delete("p1")

        class CustomBot(Bot):
            def act(self, _goal: Goal, toolbox: Toolbox) -> Action:
                toolbox.write_file(PurePosixPath("p2"), "b")
                return Action()

        self._drafter.generate_draft("hello", CustomBot(), sync=True)
        assert self._read("p1") is None

    def test_generate_delete_finalize_clean(self) -> None:
        self._write("p1", "a")
        self._repo.git.add(all=True)
        self._repo.index.commit("advance")

        class CustomBot(Bot):
            def act(self, _goal: Goal, toolbox: Toolbox) -> Action:
                toolbox.delete_file(PurePosixPath("p1"))
                return Action()

        self._drafter.generate_draft("hello", CustomBot())
        assert self._read("p1") == "a"

        self._drafter.finalize_draft(clean=True)
        assert self._read("p1") is None

    def test_revert_outside_draft(self) -> None:
        with pytest.raises(RuntimeError):
            self._drafter.revert_draft()

    def test_revert_after_branch_move(self) -> None:
        self._write("log", "11")
        self._drafter.generate_draft("hi", FakeBot(), sync=True)
        branch = self._repo.active_branch
        self._repo.git.checkout("main")
        self._repo.index.commit("advance")
        self._repo.git.checkout(branch)
        with pytest.raises(RuntimeError):
            self._drafter.revert_draft()

    def test_revert_restores_worktree(self) -> None:
        self._write("p1.txt", "a1")
        self._write("p2.txt", "b1")
        self._drafter.generate_draft("hello", FakeBot(), sync=True)
        self._write("p1.txt", "a2")
        self._drafter.revert_draft(delete=True)
        assert self._read("p1.txt") == "a1"
        assert self._read("p2.txt") == "b1"

    def test_revert_discards_unused_files(self) -> None:
        self._drafter.generate_draft("hello", FakeBot())
        assert self._read("PROMPT") is None
        self._drafter.revert_draft()
        assert self._read("PROMPT") is None

    def test_revert_keeps_untouched_files(self) -> None:
        class CustomBot(Bot):
            def act(self, _goal: Goal, toolbox: Toolbox) -> Action:
                toolbox.write_file(PurePosixPath("p2.txt"), "t2")
                toolbox.write_file(PurePosixPath("p4.txt"), "t2")
                return Action()

        self._write("p1.txt", "t0")
        self._write("p2.txt", "t0")
        self._repo.git.add(all=True)
        self._repo.index.commit("update")
        self._write("p1.txt", "t1")
        self._write("p2.txt", "t1")
        self._write("p3.txt", "t1")
        self._drafter.generate_draft("hello", CustomBot())
        self._write("p1.txt", "t3")
        self._write("p2.txt", "t3")
        self._drafter.revert_draft()

        assert self._read("p1.txt") == "t3"
        assert self._read("p2.txt") == "t0"
        assert self._read("p3.txt") == "t1"
        assert self._read("p4.txt") is None

    def test_finalize_keeps_changes(self) -> None:
        self._write("p1.txt", "a1")
        self._drafter.generate_draft("hello", FakeBot())
        self._checkout()
        self._write("p1.txt", "a2")
        self._drafter.finalize_draft()
        assert self._read("p1.txt") == "a2"
        assert self._read("PROMPT") == "hello"
