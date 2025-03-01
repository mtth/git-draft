from __future__ import annotations

import dataclasses
import git
import json
import random
from pathlib import PurePosixPath
import re
import string
import tempfile
from typing import ClassVar, Match, Self, Sequence

from .assistant import Assistant


def enclosing_repo() -> git.Repo:
    return git.Repo(search_parent_directories=True)


_random = random.Random()


@dataclasses.dataclass(frozen=True)
class _Branch:
    """Draft branch"""

    _SUFFIX_LENGTH = 8

    _name_pattern = re.compile(r"drafts/(.+)/(\w+)")

    parent: str
    suffix: str

    def __str__(self) -> str:
        return f"drafts/{self.parent}/{self.suffix}"

    @classmethod
    def _for_parent(cls, parent: str) -> _Branch:
        suffix = "".join(
            _random.choice(string.ascii_lowercase + string.digits)
            for _ in range(cls._SUFFIX_LENGTH)
        )
        return cls(parent, suffix)

    @classmethod
    def active(cls, repo: git.Repo, create=False) -> _Branch:
        match: Match | None = None
        if repo.active_branch:
            match = cls._name_pattern.fullmatch(repo.active_branch.name)
        if match:
            return _Branch(match[1], match[2])

        if not create:
            raise RuntimeError("Not currently on a draft branch")

        if not repo.active_branch:
            raise RuntimeError("No currently active branch")
        branch = cls._for_parent(repo.active_branch.name)
        ref = repo.create_head(str(branch))
        repo.git.checkout(ref)
        return branch


class _Note:
    """Structured metadata attached to a commit"""

    __prefix: ClassVar[str]

    def __init_subclass__(cls, name) -> None:
        cls.__prefix = f"{name}: "

    # https://stackoverflow.com/a/40496777

    @classmethod
    def read(cls, repo: git.Repo, ref: str) -> Self:
        for line in repo.git.notes("show", ref).splitlines():
            if line.startswith(cls.__prefix):
                data = json.loads(line[len(cls.__prefix) :])
                return cls(**data)
        raise ValueError("No matching note found")

    def write(self, repo: git.Repo, ref: str) -> None:
        assert dataclasses.is_dataclass(self)
        data = dataclasses.asdict(self)
        value = json.dumps(data, separators=(",", ":"))
        repo.git.notes(
            "append", "--no-separator", "-m", f"{self.__prefix}{value}", ref
        )


@dataclasses.dataclass(frozen=True)
class _BranchNote(_Note, name="draft-branch"):
    """Information about the current draft's branch"""

    sha: str
    dirty_sha: str | None = None


@dataclasses.dataclass(frozen=True)
class _SessionNote(_Note, name="draft-session"):
    """Information about the commit's underlying assistant session"""

    token_count: int
    walltime: float


class _Toolbox:
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
    def __init__(self, repo: git.Repo) -> None:
        self._repo = repo

    def generate_draft(
        self, prompt: str, assistant: Assistant, reset=False
    ) -> None:
        if not prompt:
            raise ValueError("Empty prompt")

        repo = self._repo
        branch = _Branch.active(repo, create=True)

        if repo.index.entries:
            if not reset:
                raise ValueError("Please commit or reset any staged changes")
            repo.index.reset()

        # TODO: draft! init commit with note

        ref = repo.commit()
        if repo.is_dirty():
            repo.git.add(all=True)
            dirty_ref = repo.index.commit("draft! sync")
            dirty_ref_sha = dirty_ref.hexsha
        else:
            dirty_ref_sha = None
        branch_note = _BranchNote(ref.hexsha, dirty_ref_sha)
        branch_note.write(repo, branch.parent)

        assistant.run(prompt, _Toolbox(repo))

        repo.index.commit(f"draft! prompt\n\n{prompt}")

    def finalize_draft(self, delete=False) -> None:
        self._exit_draft(True, delete=delete)

    def discard_draft(self, delete=False) -> None:
        self._exit_draft(False, delete=delete)

    def _exit_draft(self, apply: bool, delete=False) -> None:
        repo = self._repo
        branch = _Branch.active(repo)
        note = _BranchNote.read(repo, str(branch))

        cur_sha = repo.git.rev_parse(str(branch))
        if cur_sha != note.sha:
            raise ValueError("Parent branch has moved")

        # https://stackoverflow.com/a/15993574
        repo.git.checkout("--detach")
        if apply:
            repo.git.reset(note.sha)  # Discard index (internal) changes.
        else:
            repo.git.reset("--hard", note.dirty_sha or note.sha)
        repo.git.checkout(branch.parent)

        if delete:
            repo.git.branch("-D", str(branch))
