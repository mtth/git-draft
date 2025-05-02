"""Git wrapper"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
import dataclasses
import enum
import logging
from pathlib import Path
import subprocess
from typing import Self
import uuid


_logger = logging.getLogger(__name__)


type SHA = str


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
            message = f"Git command failed with code exit {code}: {stderr}"
            if stdout:
                message += f"\n{stdout}"
            raise GitError(message)
        return cls(code, stdout.rstrip(), stderr.rstrip())


class GitError(Exception):
    """Git command execution error"""


class _ConfigKey(enum.StrEnum):
    #: Unique identifier used to keep track of a repo. We don't just rely on
    #: its path to allow tracking to persist across repo moves.
    REPO_UUID = "repouuid"

    #: Name of the default bot to use in this repository when none is specified
    #: at the command line. Takes precedence over the default "use first"
    #: behavior.
    DEFAULT_BOT = "bot"

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
        """Returns the repo enclosing the given path"""
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
        """Runs a git command inside this repo"""
        return GitCall.sync(
            cmd,
            *args,
            stdin=stdin,
            expect_codes=expect_codes,
            working_dir=self.working_dir,
        )

    def active_branch(self) -> str | None:
        return self.git("branch", "--show-current").stdout or None

    def default_bot(self) -> str | None:
        return _get_config_value(_ConfigKey.DEFAULT_BOT, self.working_dir)


def _get_config_value(key: _ConfigKey, working_dir: Path) -> str | None:
    call = GitCall.sync(
        "config",
        "get",
        key.fullname,
        working_dir=working_dir,
        expect_codes=(),
    )
    return None if call.code else call.stdout


def _ensure_repo_uuid(working_dir: Path) -> uuid.UUID:
    value = _get_config_value(_ConfigKey.REPO_UUID, working_dir)
    if value:
        return uuid.UUID(value)
    repo_uuid = uuid.uuid4()
    GitCall.sync(
        "config",
        "set",
        _ConfigKey.REPO_UUID.fullname,
        str(repo_uuid),
        working_dir=working_dir,
    )
    _logger.debug("Set repo UUID. [uuid=%s]", repo_uuid)
    return repo_uuid


def null_delimited(arg: str) -> Iterator[str]:
    return (item for item in arg.split("\x00") if item)
