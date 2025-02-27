from __future__ import annotations

import dataclasses
import git
import random
from pathlib import PurePosixPath
import re
import string
import tempfile
from typing import Match, Sequence

from .backend import NewFileBackend


def _enclosing_repo() -> git.Repo:
    return git.Repo(search_parent_directories=True)


_random = random.Random()

_SUFFIX_LENGTH = 8

_branch_name_pattern = re.compile(r"drafts/(.+)/(\w+)")


@dataclasses.dataclass(frozen=True)
class _DraftBranch:
    parent: str
    suffix: str
    repo: git.Repo

    def __str__(self) -> str:
        return f"drafts/{self.parent}/{self.suffix}"

    @classmethod
    def create(cls, repo: git.Repo) -> _DraftBranch:
        if not repo.active_branch:
            raise RuntimeError("No currently active branch")
        suffix = "".join(
            _random.choice(string.ascii_lowercase + string.digits)
            for _ in range(_SUFFIX_LENGTH)
        )
        return cls(repo.active_branch.name, suffix, repo)

    @classmethod
    def active(cls, repo: git.Repo) -> _DraftBranch:
        match: Match | None = None
        if repo.active_branch:
            match = _branch_name_pattern.fullmatch(repo.active_branch.name)
        if not match:
            raise RuntimeError("Not currently on a draft branch")
        return _DraftBranch(match[1], match[2], repo)


@dataclasses.dataclass(frozen=True)
class _CommitNotes:
    # https://stackoverflow.com/a/40496777
    pass


def create_draft() -> None:
    repo = _enclosing_repo()
    draft_branch = _DraftBranch.create(repo)
    ref = repo.create_head(str(draft_branch))
    repo.git.checkout(ref)


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


def extend_draft(prompt: str) -> None:
    repo = _enclosing_repo()
    _ = _DraftBranch.active(repo)

    if repo.is_dirty():
        repo.git.add(all=True)
        repo.index.commit("draft! sync")

    NewFileBackend().run(prompt, _Toolbox(repo))


def apply_draft(delete=False) -> None:
    repo = _enclosing_repo()
    branch = _DraftBranch.active(repo)

    # TODO: Check that parent has not moved. We could do this for example by
    # adding a note to the draft branch with the original branch's commit ref.

    # https://stackoverflow.com/a/15993574
    repo.git.checkout("--detach")
    repo.git.reset("--soft", branch.parent)
    repo.git.checkout(branch.parent)

    if delete:
        repo.git.branch("-D", str(branch))
