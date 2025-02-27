from __future__ import annotations

import dataclasses
import git
import random
import re
import string


def _enclosing_repo() -> git.Repo:
    return git.Repo(search_parent_directories=True)


_random = random.Random()

_SUFFIX_LENGTH = 6

_name_pattern = re.compile(r"\w+", re.ASCII)

_branch_pattern = re.compile("drafts/(.+)/(\w+)-(\w+)", re.ASCII)


@dataclasses.dataclass(frozen=True)
class _DraftBranch:
    parent: str
    name: str
    suffix: str

    def __str__(self) -> str:
        return f"drafts/{self.parent}/{self.name}-{self.suffix}"

    @classmethod
    def named(cls, name: str, parent: str) -> _DraftBranch:
        if not _name_pattern.fullmatch(name):
            raise ValueError(f"Invalid draft name: {name}")
        suffix = "".join(
            _random.choice(string.ascii_lowercase + string.digits)
            for _ in range(_SUFFIX_LENGTH)
        )
        return cls(parent, name, suffix)

    @classmethod
    def active(cls, repo: git.Repo) -> _DraftBranch:
        branch: _DraftBranch | None = None
        if repo.active_branch:
            branch = cls.from_string(repo.active_branch.name)
        if not branch:
            raise ValueError("Not currently on a draft branch")
        return branch

    @classmethod
    def from_string(cls, s: str) -> _DraftBranch | None:
        match = _branch_pattern.fullmatch(s)
        if not match:
            return None
        return _DraftBranch(match[1], match[2], match[3])


def create_draft(name: str) -> None:
    repo = _enclosing_repo()
    draft_branch = _DraftBranch.named(name, repo.active_branch.name)
    ref = repo.create_head(str(draft_branch))
    repo.git.checkout(ref)


def extend_draft(prompt: str) -> None:
    repo = _enclosing_repo()
    branch = _DraftBranch.active(repo)

    if repo.is_dirty():
        repo.git.add(all=True)
        repo.index.commit("draft! sync")

    # send request to backend...
    import time

    time.sleep(2)

    # Add files to index.
    import random

    name = f"foo-{random.randint(1,100)}"
    with open(name, "w") as writer:
        writer.write("hi")
    repo.git.hash_object("-w", name)
    repo.git.update_index("--add", "--info-only", name)

    repo.index.commit(f"draft! prompt: {prompt}")
