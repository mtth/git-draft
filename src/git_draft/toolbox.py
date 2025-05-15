"""Functionality available to bots"""

from __future__ import annotations

import collections
from collections.abc import Callable, Sequence
import dataclasses
import logging
from pathlib import PurePosixPath
import tempfile
from typing import Protocol, Self, override

from .common import UnreachableError
from .git import SHA, GitError, Repo, null_delimited


_logger = logging.getLogger(__name__)


class Toolbox:
    """File-system intermediary

    Note that the toolbox is not thread-safe. Concurrent operations should be
    serialized by the caller.
    """

    # TODO: Something similar to https://aider.chat/docs/repomap.html,
    # including inferring the most important files, and allowing returning
    # signature-only versions.

    # TODO: Support a diff-based edit method.
    # https://gist.github.com/noporpoise/16e731849eb1231e86d78f9dfeca3abc

    def __init__(self, visitors: Sequence[ToolVisitor] | None = None) -> None:
        self._visitors = visitors or []

    def _dispatch(self, effect: Callable[[ToolVisitor], None]) -> None:
        for visitor in self._visitors:
            effect(visitor)

    def list_files(self, reason: str | None = None) -> Sequence[PurePosixPath]:
        paths = self._list()
        self._dispatch(lambda v: v.on_list_files(paths, reason))
        return paths

    def read_file(
        self,
        path: PurePosixPath,
        reason: str | None = None,
    ) -> str | None:
        try:
            contents = self._read(path)
        except FileNotFoundError:
            contents = None
        self._dispatch(lambda v: v.on_read_file(path, contents, reason))
        return contents

    def write_file(
        self,
        path: PurePosixPath,
        contents: str,
        reason: str | None = None,
    ) -> None:
        self._dispatch(lambda v: v.on_write_file(path, contents, reason))
        return self._write(path, contents)

    def delete_file(
        self,
        path: PurePosixPath,
        reason: str | None = None,
    ) -> None:
        self._dispatch(lambda v: v.on_delete_file(path, reason))
        self._delete(path)

    def rename_file(
        self,
        src_path: PurePosixPath,
        dst_path: PurePosixPath,
        reason: str | None = None,
    ) -> None:
        self._dispatch(lambda v: v.on_rename_file(src_path, dst_path, reason))
        self._rename(src_path, dst_path)

    def _list(self) -> Sequence[PurePosixPath]:  # pragma: no cover
        raise NotImplementedError()

    def _read(self, path: PurePosixPath) -> str:  # pragma: no cover
        raise NotImplementedError()

    def _write(
        self, path: PurePosixPath, contents: str
    ) -> None:  # pragma: no cover
        raise NotImplementedError()

    def _delete(self, path: PurePosixPath) -> None:  # pragma: no cover
        raise NotImplementedError()

    def _rename(
        self, src_path: PurePosixPath, dst_path: PurePosixPath
    ) -> None:
        # We can provide a default implementation here.
        contents = self._read(src_path)
        self._write(dst_path, contents)
        self._delete(src_path)


class ToolVisitor(Protocol):
    """Tool usage hook"""

    def on_list_files(
        self, paths: Sequence[PurePosixPath], reason: str | None
    ) -> None: ...  # pragma: no cover

    def on_read_file(
        self, path: PurePosixPath, contents: str | None, reason: str | None
    ) -> None: ...  # pragma: no cover

    def on_write_file(
        self, path: PurePosixPath, contents: str, reason: str | None
    ) -> None: ...  # pragma: no cover

    def on_delete_file(
        self, path: PurePosixPath, reason: str | None
    ) -> None: ...  # pragma: no cover

    def on_rename_file(
        self,
        src_path: PurePosixPath,
        dst_path: PurePosixPath,
        reason: str | None,
    ) -> None: ...  # pragma: no cover


class NoopToolbox(Toolbox):
    """No-op read-only toolbox"""

    @override
    def _list(self) -> Sequence[PurePosixPath]:
        return []

    @override
    def _read(self, _path: PurePosixPath) -> str:
        raise RuntimeError()

    @override
    def _write(self, _path: PurePosixPath, _contents: str) -> None:
        raise RuntimeError()

    @override
    def _delete(self, _path: PurePosixPath) -> None:
        raise RuntimeError()


class RepoToolbox(Toolbox):
    """Git-repo backed toolbox implementation

    All files are directly read from and written to an standalone tree. This
    allows concurrent editing without interference with the working directory
    or index.

    This toolbox is not thread-safe.
    """

    def __init__(
        self,
        repo: Repo,
        start_rev: SHA,
        visitors: Sequence[ToolVisitor] | None = None,
    ) -> None:
        super().__init__(visitors)
        call = repo.git("rev-parse", "--verify", f"{start_rev}^{{tree}}")
        self._tree_sha = call.stdout
        self._tree_updates = list[_TreeUpdate]()
        self._repo = repo

    @classmethod
    def for_working_dir(cls, repo: Repo) -> tuple[Self, bool]:
        index_tree_sha = repo.git("write-tree").stdout
        toolbox = cls(repo, index_tree_sha)

        # Apply any changes from the working directory.
        deleted = set[SHA]()
        for path in null_delimited(repo.git("ls-files", "-dz").stdout):
            deleted.add(path)
            toolbox._delete(PurePosixPath(path))
        for path in null_delimited(
            repo.git("ls-files", "-moz", "--exclude-standard").stdout
        ):
            if path in deleted:
                continue  # Deleted files also show up as modified
            toolbox._write_from_disk(PurePosixPath(path), path)

        head_tree_sha = repo.git("rev-parse", "HEAD^{tree}").stdout
        return toolbox, toolbox.tree_sha() != head_tree_sha

    def with_visitors(self, visitors: Sequence[ToolVisitor]) -> Self:
        return self.__class__(self._repo, self.tree_sha(), visitors)

    def tree_sha(self) -> SHA:
        if updates := self._tree_updates:
            self._tree_sha = _update_tree(self._tree_sha, updates, self._repo)
            updates.clear()
        return self._tree_sha

    @override
    def _list(self) -> Sequence[PurePosixPath]:
        call = self._repo.git("ls-tree", "-rz", "--name-only", self.tree_sha())
        return [PurePosixPath(p) for p in null_delimited(call.stdout)]

    @override
    def _read(self, path: PurePosixPath) -> str:
        try:
            return self._repo.git("show", f"{self.tree_sha()}:{path}").stdout
        except GitError as exc:
            msg = str(exc)
            if "does not exist in" in msg or "exists on disk, but not" in msg:
                raise FileNotFoundError(f"{path} does not exist")
            raise

    @override
    def _write(self, path: PurePosixPath, contents: str) -> None:
        # Update the index without touching the worktree.
        # https://stackoverflow.com/a/25352119
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            temp.write(contents.encode("utf8"))
            temp.close()
            self._write_from_disk(path, temp.name)

    def _write_from_disk(
        self, path: PurePosixPath, contents_path: str
    ) -> None:
        blob_sha = self._repo.git(
            "hash-object",
            "-w",
            "--path",
            str(path),
            contents_path,
        ).stdout
        self._tree_updates.append(_WriteBlob(path, blob_sha))

    @override
    def _delete(self, path: PurePosixPath) -> None:
        self._tree_updates.append(_DeleteBlob(path))


class _TreeUpdate:
    """Generic tree update"""


@dataclasses.dataclass(frozen=True)
class _WriteBlob(_TreeUpdate):
    path: PurePosixPath
    blob_sha: SHA


@dataclasses.dataclass(frozen=True)
class _DeleteBlob(_TreeUpdate):
    path: PurePosixPath


def _update_tree(sha: SHA, updates: Sequence[_TreeUpdate], repo: Repo) -> SHA:
    if not updates:
        return sha

    blob_shas = collections.defaultdict[PurePosixPath, dict[str, str]](dict)
    for update in updates:
        match update:
            case _WriteBlob(path, blob_sha):
                blob_shas[path.parent][path.name] = blob_sha
            case _DeleteBlob(path):
                blob_shas[path.parent][path.name] = ""
            case _:
                raise UnreachableError()

    def visit_tree(sha: SHA, path: PurePosixPath) -> SHA:
        old_lines = null_delimited(repo.git("ls-tree", "-z", sha).stdout)
        new_blob_shas = blob_shas[path]

        new_lines = list[str]()
        for line in old_lines:
            old_prefix, name = line.split("\t", 1)
            mode, otype, old_sha = old_prefix.split(" ")
            match otype:
                case "blob":
                    new_sha = new_blob_shas.pop(name, old_sha)
                    if new_sha:
                        new_lines.append(f"{mode} blob {new_sha}\t{name}")
                case "tree":
                    new_sha = visit_tree(old_sha, path / name)
                    new_lines.append(f"040000 tree {new_sha}\t{name}")
                case _:
                    raise UnreachableError()

        for name, blob_sha in new_blob_shas.items():
            if blob_sha:
                new_lines.append(f"100644 blob {blob_sha}\t{name}")
            else:
                _logger.warning("Unmatched deletion. [path=%s]", path / name)

        if new_lines == old_lines:
            return sha

        return repo.git("mktree", "-z", stdin="\x00".join(new_lines)).stdout

    return visit_tree(sha, PurePosixPath("."))
