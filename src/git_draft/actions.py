from __future__ import annotations

import dataclasses
import git
import random
import string


def _enclosing_repo() -> git.Repo:
    return git.Repo(search_parent_directories=True)


_random = random.Random()

_SUFFIX_LENGTH = 6


@dataclasses.dataclass(frozen=True)
class _DraftBranch:
    parent: str
    name: str
    suffix: str

    def __str__(self) -> str:
        return f"drafts/{self.parent}/{self.name}-{self.suffix}"

    @classmethod
    def named(cls, name: str, parent: str) -> _DraftBranch:
        suffix = "".join(
            _random.choice(string.ascii_lowercase + string.digits)
            for _ in range(_SUFFIX_LENGTH)
        )
        return cls(parent, name, suffix)

    @classmethod
    def active(cls, repo: git.Repo) -> _DraftBranch | None:
        raise NotImplementedError()  # TODO

    @classmethod
    def from_string(cls, s: str) -> _DraftBranch:
        raise NotImplementedError()  # TODO


def create_draft(name: str) -> None:
    repo = _enclosing_repo()
    draft_branch = _DraftBranch.named(name, repo.active_branch.name)
    ref = repo.create_head(str(draft_branch))
    repo.git.checkout(ref)
    if repo.is_dirty():
        repo.git.add(all=True)
        repo.index.commit("draft! sync")


def apply_draft() -> None:
    repo = _enclosing_repo()
