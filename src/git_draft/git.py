"""Git wrapper"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
from pathlib import Path
import subprocess
from typing import Self


@dataclasses.dataclass(frozen=True)
class Commit:
    """Commit newtype"""

    sha: str

    def __str__(self) -> str:
        return self.sha


class Repo:
    """Git repository"""

    def __init__(self, working_dir: Path) -> None:
        self.working_dir = working_dir

    @classmethod
    def enclosing(cls, path: Path) -> Self:
        git = Git.run("-C", str(path), "rev-parse", "--show-toplevel")
        return cls(Path(git.stdout))

    def git(
        self,
        cmd: str,
        *args: str,
        stdin: str | None = None,
        expect_codes: Sequence[int] = (0,),
    ) -> Git:
        return Git.run(
            "-C",
            str(self.working_dir),
            cmd,
            *args,
            stdin=stdin,
            expect_codes=expect_codes,
        )

    def active_branch(self) -> str | None:
        return self.git("branch", "--show-current").stdout or None

    def checkout_new_branch(self, name: str) -> None:
        self.git("checkout", "-b", name)

    def has_staged_changes(self) -> bool:
        git = self.git("diff", "--quiet", "--staged", expect_codes=())
        return git.code != 0

    def head_commit(self) -> Commit:
        sha = self.git("rev-parse", "HEAD").stdout
        return Commit(sha)

    def create_commit(self, message: str, skip_hooks: bool = False) -> Commit:
        args = ["commit", "--allow-empty", "-m", message]
        if skip_hooks:
            args.append("--no-verify")
        self.git(*args)
        return self.head_commit()


@dataclasses.dataclass(frozen=True)
class Git:
    """Git command execution result"""

    code: int
    stdout: str
    stderr: str

    @classmethod
    def run(
        cls,
        *args: str,
        stdin: str | None = None,
        executable: str = "git",
        expect_codes: Sequence[int] = (0,),
    ) -> Self:
        popen = subprocess.Popen(
            [executable, *args],
            encoding="utf8",
            stdin=None if stdin is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = popen.communicate(input=stdin)
        code = popen.returncode
        if expect_codes and code not in expect_codes:
            raise GitError(f"Git command failed with code {code}: {stderr}")
        return cls(code, stdout.rstrip(), stderr.rstrip())


class GitError(Exception):
    """Git command execution error"""
