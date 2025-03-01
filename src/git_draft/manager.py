from __future__ import annotations

import dataclasses
import git
import json
import logging
from pathlib import PurePosixPath
import re
import tempfile
import time
from typing import Callable, ClassVar, Match, Self, Sequence

from .assistants import Assistant, Toolbox


_logger = logging.getLogger(__name__)


def enclosing_repo(path: str | None = None) -> git.Repo:
    """Returns the repository to which the given path belongs"""
    return git.Repo(path, search_parent_directories=True)


class _Note:
    """Structured metadata attached to a commit"""

    # https://stackoverflow.com/a/40496777

    __prefix: ClassVar[str]

    def __init_subclass__(cls, name) -> None:
        cls.__prefix = f"{name}: "

    @classmethod
    def read(cls, repo: git.Repo, ref: str) -> Self | None:
        for line in repo.git.notes("show", ref).splitlines():
            if line.startswith(cls.__prefix):
                data = json.loads(line[len(cls.__prefix) :])
                _logger.debug("Read %r note. [ref=%s]", cls.__prefix, ref)
                return cls(**data)
        return None

    def write(self, repo: git.Repo, ref: str) -> None:
        assert dataclasses.is_dataclass(self)
        data = dataclasses.asdict(self)
        value = json.dumps(data, separators=(",", ":"))
        repo.git.notes(
            "append", "--no-separator", "-m", f"{self.__prefix}{value}", ref
        )
        _logger.debug("Write %r note. [ref=%s]", self.__prefix, ref)


@dataclasses.dataclass(frozen=True)
class _InitNote(_Note, name="draft-init"):
    """Information about the current draft's branch"""

    origin_branch: str
    sync_sha: str | None


@dataclasses.dataclass(frozen=True)
class _SessionNote(_Note, name="draft-session"):
    """Information about a commit's underlying assistant session"""

    token_count: int
    walltime: float


@dataclasses.dataclass(frozen=True)
class _Branch:
    """Draft branch"""

    _name_pattern = re.compile(r"drafts/(.+)")

    init_shortsha: str
    init_note: _InitNote

    @property
    def name(self) -> str:
        return f"drafts/{self.init_shortsha}"

    def needs_rebase(self, repo: git.Repo) -> bool:
        if not self.init_note.sync_sha:
            return False
        init_commit = repo.commit(self.init_shortsha)
        (origin_commit,) = init_commit.parents
        head_commit = repo.commit(self.init_note.origin_branch)
        return origin_commit != head_commit

    def __str__(self) -> str:
        return self.name

    @classmethod
    def create(cls, repo: git.Repo, sync: Callable[[], str | None]) -> _Branch:
        if not repo.active_branch:
            raise RuntimeError("No currently active branch")
        origin_branch = repo.active_branch.name

        repo.git.checkout("--detach")
        commit = repo.index.commit("draft! init")
        init_shortsha = commit.hexsha[:7]
        init_note = _InitNote(origin_branch, sync())
        init_note.write(repo, init_shortsha)

        branch = _Branch(init_shortsha, init_note)
        branch_ref = repo.create_head(branch.name)
        repo.git.checkout(branch_ref)
        return branch

    @classmethod
    def active(cls, repo: git.Repo) -> _Branch | None:
        match: Match | None = None
        if repo.active_branch:
            match = cls._name_pattern.fullmatch(repo.active_branch.name)
        if not match:
            return None
        init_shortsha = match[1]
        init_note = _InitNote.read(repo, init_shortsha)
        assert init_note
        return _Branch(init_shortsha, init_note)


class _Toolbox(Toolbox):
    """Git-index backed toolbox

    All files are directly read from and written to the index. This allows
    concurrent editing without interference.
    """

    def __init__(self, repo: git.Repo) -> None:
        self._repo = repo

    def list_files(self) -> Sequence[PurePosixPath]:
        # Show staged files.
        return self._repo.git.ls_files()

    def read_file(self, path: PurePosixPath) -> str:
        # Read the file from the index.
        return self._repo.git.show(f":{path}")

    def write_file(self, path: PurePosixPath, data: str) -> None:
        # Update the index without touching the worktree.
        # https://stackoverflow.com/a/25352119
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            temp.write(data.encode("utf8"))
            temp.close()
            sha = self._repo.git.hash_object("-w", "--path", path, temp.name)
            mode = 644  # TODO: Read from original file if it exists.
            self._repo.git.update_index(
                "--add", "--cacheinfo", f"{mode},{sha},{path}"
            )


class Manager:
    """Draft state manager"""

    def __init__(self, repo: git.Repo) -> None:
        self._repo = repo

    def generate_draft(
        self, prompt: str, assistant: Assistant, checkout=False, reset=False
    ) -> None:
        if not prompt.strip():
            raise ValueError("Empty prompt")
        if self._repo.is_dirty(working_tree=False):
            if not reset:
                raise ValueError("Please commit or reset any staged changes")
            self._repo.index.reset()

        branch = _Branch.active(self._repo)
        if branch:
            _logger.debug("Reusing active branch %s.", branch)
            self._sync()
        else:
            branch = _Branch.create(self._repo, self._sync)
            _logger.debug("Created branch %s.", branch)

        start_time = time.perf_counter()
        session = assistant.run(prompt, _Toolbox(self._repo))
        end_time = time.perf_counter()
        commit = self._repo.index.commit(f"draft! prompt\n\n{prompt}")
        note = _SessionNote(session.token_count, end_time - start_time)
        note.write(self._repo, commit.hexsha)
        _logger.info("Generated draft. [token_count=%s]", session.token_count)

        if checkout:
            self._repo.git.checkout("--", ".")

    def finalize_draft(self, delete=False) -> None:
        self._exit_draft(True, delete=delete)

    def discard_draft(self, delete=False) -> None:
        self._exit_draft(False, delete=delete)

    def _sync(self) -> str | None:
        if not self._repo.is_dirty(untracked_files=True):
            return None
        self._repo.git.add(all=True)
        ref = self._repo.index.commit("draft! sync")
        return ref.hexsha

    def _exit_draft(self, apply: bool, delete=False) -> None:
        branch = _Branch.active(self._repo)
        if not branch:
            raise RuntimeError("Not currently on a draft branch")
        if not apply and branch.needs_rebase(self._repo):
            raise ValueError("Parent branch has moved, please rebase")

        # https://stackoverflow.com/a/15993574
        note = branch.init_note
        self._repo.git.checkout("--detach")
        if apply:
            # We discard index (internal) changes
            self._repo.git.reset(note.origin_branch)
        else:
            self._repo.git.reset("--hard", note.sync_sha or note.origin_branch)
        self._repo.git.checkout(note.origin_branch)

        if delete:
            self._repo.git.branch("-D", branch.name)
