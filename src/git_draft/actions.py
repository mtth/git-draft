from __future__ import annotations

import dataclasses
import git
import random
import re
import string
from typing import Match


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
    pass


def create_draft() -> None:
    repo = _enclosing_repo()
    draft_branch = _DraftBranch.create(repo)
    ref = repo.create_head(str(draft_branch))
    repo.git.checkout(ref)


def extend_draft(prompt: str) -> None:
    repo = _enclosing_repo()
    _ = _DraftBranch.active(repo)

    if repo.is_dirty():
        repo.git.add(all=True)
        repo.index.commit("draft! sync")

    # send request to backend...
    import time

    time.sleep(2)

    # Add files to index.
    import random

    name = f"foo-{random.randint(1, 100)}"
    with open(name, "w") as writer:
        writer.write("hi")
    repo.git.hash_object("-w", name)
    repo.git.update_index("--add", "--info-only", name)

    repo.index.commit(f"draft! prompt: {prompt}")


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
