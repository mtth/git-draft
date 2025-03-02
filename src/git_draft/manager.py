from __future__ import annotations

import dataclasses
import git
import logging
from pathlib import PurePosixPath
import re
import tempfile
import time
from typing import Match, Sequence

from .assistants import Assistant, Toolbox
from .common import Store, random_id, sql


_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _Branch:
    """Draft branch"""

    _name_pattern = re.compile(r"drafts/(.+)")

    suffix: str

    @property
    def name(self) -> str:
        return f"drafts/{self.suffix}"

    def __str__(self) -> str:
        return self.name

    @classmethod
    def active(cls, repo: git.Repo) -> _Branch | None:
        match: Match | None = None
        if repo.active_branch:
            match = cls._name_pattern.fullmatch(repo.active_branch.name)
        if not match:
            return None
        return _Branch(match[1])

    @staticmethod
    def new_suffix():
        return random_id(9)


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

    def write_file(self, path: PurePosixPath, contents: str) -> None:
        # Update the index without touching the worktree.
        # https://stackoverflow.com/a/25352119
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            temp.write(contents.encode("utf8"))
            temp.close()
            sha = self._repo.git.hash_object("-w", "--path", path, temp.name)
            mode = 644  # TODO: Read from original file if it exists.
            self._repo.git.update_index(
                "--add", "--cacheinfo", f"{mode},{sha},{path}"
            )


class Manager:
    """Draft state manager"""

    def __init__(self, store: Store, repo: git.Repo) -> None:
        with store.cursor() as cursor:
            cursor.executescript(sql("create-tables"))
        self._store = store
        self._repo = repo

    @classmethod
    def create(cls, store: Store, path: str | None = None) -> Manager:
        return cls(store, git.Repo(path, search_parent_directories=True))

    def _create_branch(self, sync: bool) -> _Branch:
        if not self._repo.active_branch:
            raise RuntimeError("No currently active branch")
        origin_branch = self._repo.active_branch.name
        origin_sha = self._repo.commit().hexsha

        self._repo.git.checkout("--detach")
        sync_sha = self._sync() if sync else None
        suffix = _Branch.new_suffix()

        with self._store.cursor() as cursor:
            cursor.execute(
                sql("add-branch"),
                {
                    "suffix": suffix,
                    "origin_branch": origin_branch,
                    "origin_sha": origin_sha,
                    "sync_sha": sync_sha,
                },
            )

        branch = _Branch(suffix)
        branch_ref = self._repo.create_head(branch.name)
        self._repo.git.checkout(branch_ref)
        return branch

    def generate_draft(
        self,
        prompt: str,
        assistant: Assistant,
        checkout=False,
        reset=False,
        sync=False,
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
            if sync:
                self._sync()
        else:
            branch = self._create_branch(sync)
            _logger.debug("Created branch %s.", branch)

        with self._store.cursor() as cursor:
            [(prompt_id,)] = cursor.execute(
                sql("add-prompt"),
                {
                    "branch_suffix": branch.suffix,
                    "contents": prompt,
                },
            )

        start_time = time.perf_counter()
        session = assistant.run(prompt, _Toolbox(self._repo))
        end_time = time.perf_counter()
        commit = self._repo.index.commit(f"draft! prompt\n\n{prompt}")

        with self._store.cursor() as cursor:
            cursor.execute(
                sql("add-commit"),
                {
                    "sha": commit.hexsha,
                    "prompt_id": prompt_id,
                    "token_count": session.token_count,
                    "walltime": end_time - start_time,
                },
            )
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

        with self._store.cursor() as cursor:
            [(origin_branch, origin_sha, sync_sha)] = cursor.execute(
                sql("get-branch-by-suffix"), {"suffix": branch.suffix}
            )

        if (
            not apply
            and sync_sha
            and self._repo.commit(origin_branch).hexsha != origin_sha
        ):
            raise ValueError("Parent branch has moved, please rebase")

        # We do a small dance to move back to the original branch, keeping the
        # draft branch untouched. See https://stackoverflow.com/a/15993574 for
        # the inspiration.
        self._repo.git.checkout("--detach")
        self._repo.git.reset("--mixed" if apply else "--hard", origin_branch)
        self._repo.git.checkout(origin_branch)

        if not apply and sync_sha:
            self._repo.git.checkout(sync_sha, "--", ".")
        if delete:
            self._repo.git.branch("-D", branch.name)
