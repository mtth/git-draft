"""Git wrapper"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import enum
import logging
from pathlib import Path
import subprocess
from typing import Self
import uuid


_logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Commit:
    """Commit newtype"""

    sha: str

    def __str__(self) -> str:
        return self.sha


class _ConfigKey(enum.StrEnum):
    REPO_UUID = "repouuid"

    @property
    def fullname(self) -> str:
        return f"draft.{self.value}"


class Repo:
    """Git repository"""

    def __init__(self, working_dir: Path, uuid: uuid.UUID) -> None:
        self.working_dir = working_dir
        self.uuid = uuid

    @classmethod
    def enclosing(cls, path: Path) -> Self:
        call = GitCall.sync("rev-parse", "--show-toplevel", working_dir=path)
        working_dir = Path(call.stdout)
        uuid = _ensure_repo_uuid(working_dir)
        return cls(working_dir, uuid)

    def git(
        self,
        cmd: str,
        *args: str,
        stdin: str | None = None,
        expect_codes: Sequence[int] = (0,),
    ) -> GitCall:
        return GitCall.sync(
            cmd,
            *args,
            stdin=stdin,
            expect_codes=expect_codes,
            working_dir=self.working_dir,
        )

    def active_branch(self) -> str | None:
        return self.git("branch", "--show-current").stdout or None

    def checkout_new_branch(self, name: str) -> None:
        self.git("checkout", "-b", name)

    def has_staged_changes(self) -> bool:
        call = self.git("diff", "--quiet", "--staged", expect_codes=())
        return call.code != 0

    def head_commit(self) -> Commit:
        sha = self.git("rev-parse", "HEAD").stdout
        return Commit(sha)

    def create_commit(self, message: str, skip_hooks: bool = False) -> Commit:
        args = ["commit", "--allow-empty", "-m", message]
        if skip_hooks:
            args.append("--no-verify")
        self.git(*args)
        return self.head_commit()


def _ensure_repo_uuid(working_dir: Path) -> uuid.UUID:
    call = GitCall.sync(
        "config",
        "get",
        _ConfigKey.REPO_UUID.fullname,
        working_dir=working_dir,
        expect_codes=(),
    )
    if call.code == 0:
        return uuid.UUID(call.stdout)
    repo_uuid = uuid.uuid4()
    GitCall.sync(
        "config",
        "set",
        _ConfigKey.REPO_UUID.fullname,
        str(repo_uuid),
        working_dir=working_dir,
    )
    return repo_uuid


@dataclasses.dataclass(frozen=True)
class GitCall:
    """Git command execution result"""

    code: int
    stdout: str
    stderr: str

    @classmethod
    def sync(
        cls,
        *args: str,
        stdin: str | None = None,
        executable: str = "git",
        expect_codes: Sequence[int] = (0,),
        working_dir: Path | None = None,
    ) -> Self:
        """Run a git command synchronously"""
        _logger.debug(
            "Running git command. [args=%r, cwd=%r]", args, working_dir
        )
        popen = subprocess.Popen(
            [executable, *args],
            encoding="utf8",
            stdin=None if stdin is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=working_dir,
        )
        stdout, stderr = popen.communicate(input=stdin)
        code = popen.returncode
        if expect_codes and code not in expect_codes:
            raise GitError(f"Git command failed with code {code}: {stderr}")
        return cls(code, stdout.rstrip(), stderr.rstrip())


class GitError(Exception):
    """Git command execution error"""
