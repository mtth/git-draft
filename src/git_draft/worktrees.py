"""Worktree implementations"""

import collections
from collections.abc import Iterator, Sequence
import contextlib
import dataclasses
import logging
from pathlib import Path, PurePosixPath
import tempfile
from typing import Self, override

from .bots import Worktree
from .common import UnreachableError
from .events import Event, EventConsumer, worktree_events
from .git import SHA, GitError, Repo, null_delimited


_logger = logging.getLogger(__name__)


class EmptyWorktree(Worktree):
    """No-op read-only work tree

    This tree is used when gathering template metadata.
    """

    @override
    def list_files(self) -> Sequence[PurePosixPath]:
        return []

    @override
    def read_file(self, path: PurePosixPath) -> str | None:
        raise RuntimeError()

    @override
    def write_file(self, path: PurePosixPath, contents: str) -> None:
        raise RuntimeError()

    @override
    def delete_file(self, path: PurePosixPath) -> None:
        raise RuntimeError()

    @override
    def rename_file(
        self, src_path: PurePosixPath, dst_path: PurePosixPath
    ) -> None:
        raise RuntimeError()

    @override
    def edit_files(self) -> contextlib.AbstractContextManager[Path]:
        raise RuntimeError()


class GitWorktree(Worktree):
    """Git-backed worktree implementation

    All files are directly read from and written to a standalone tree. This
    allows concurrent editing without interference with the working directory
    or index.

    This implementation is not thread-safe.
    """

    # TODO: Something similar to https://aider.chat/docs/repomap.html,
    # including inferring the most important files, and allowing returning
    # signature-only versions.

    # TODO: Support a diff-based edit method.
    # https://gist.github.com/noporpoise/16e731849eb1231e86d78f9dfeca3abc

    def __init__(
        self,
        repo: Repo,
        start_rev: SHA,
        event_consumer: EventConsumer | None = None,
    ) -> None:
        call = repo.git("rev-parse", "--verify", f"{start_rev}^{{tree}}")
        self._sha = call.stdout
        self._updates = list[_Update]()
        self._repo = repo
        self._event_consumer = event_consumer

    @classmethod
    def for_working_dir(cls, repo: Repo) -> tuple[Self, bool]:
        index_tree_sha = repo.git("write-tree").stdout
        tree = cls(repo, index_tree_sha)
        tree._sync_updates()  # Apply any changes from the working directory
        head_tree_sha = repo.git("rev-parse", "HEAD^{tree}").stdout
        return tree, tree.sha() != head_tree_sha

    def _sync_updates(self, *, worktree_path: Path | None = None) -> None:
        repo = self._repo
        if worktree_path:
            repo = Repo(worktree_path)

        def ls_files(*args: str) -> Iterator[str]:
            return null_delimited(repo.git("ls-files", *args).stdout)

        deleted = set[str]()
        for path_str in ls_files("-dz"):
            deleted.add(path_str)
            self._delete(PurePosixPath(path_str))
        for path_str in ls_files("-moz", "--exclude-standard"):
            if path_str in deleted:
                continue  # Deleted files also show up as modified
            self._write_from_disk(
                PurePosixPath(path_str),
                worktree_path / path_str if worktree_path else Path(path_str),
            )

    def with_event_consumer(self, event_consumer: EventConsumer) -> Self:
        return self.__class__(self._repo, self.sha(), event_consumer)

    def sha(self) -> SHA:
        if updates := self._updates:
            self._sha = _update_tree(self._sha, updates, self._repo)
            updates.clear()
        return self._sha

    def _dispatch(self, event: Event) -> None:
        if consumer := self._event_consumer:
            consumer.on_event(event)

    @override
    def list_files(self) -> Sequence[PurePosixPath]:
        paths = self._list()
        self._dispatch(worktree_events.ListFiles(len(paths)))
        return paths

    @override
    def read_file(self, path: PurePosixPath) -> str | None:
        try:
            contents = self._read(path)
        except FileNotFoundError:
            contents = None
        self._dispatch(
            worktree_events.ReadFile(path, len(contents) if contents else None)
        )
        return contents

    @override
    def write_file(self, path: PurePosixPath, contents: str) -> None:
        self._dispatch(worktree_events.WriteFile(path, len(contents)))
        return self._write(path, contents)

    @override
    def delete_file(self, path: PurePosixPath) -> None:
        self._dispatch(worktree_events.DeleteFile(path))
        self._delete(path)

    @override
    def rename_file(
        self,
        src_path: PurePosixPath,
        dst_path: PurePosixPath,
    ) -> None:
        """Rename a single file"""
        self._dispatch(worktree_events.RenameFile(src_path, dst_path))
        contents = self._read(src_path)
        self._write(dst_path, contents)
        self._delete(src_path)

    @override
    @contextlib.contextmanager
    def edit_files(self) -> Iterator[Path]:
        """Creates a temporary folder with editable copies of all files

        All updates are synced back afterwards. Other operations should not be
        performed concurrently as they may be stale or lost.
        """
        self._dispatch(worktree_events.StartEditingFiles())
        with self._edit() as path:
            yield path
        # TODO: Expose updated files to hook?
        self._dispatch(worktree_events.StopEditingFiles())

    def _list(self) -> Sequence[PurePosixPath]:
        call = self._repo.git("ls-tree", "-rz", "--name-only", self.sha())
        return [PurePosixPath(p) for p in null_delimited(call.stdout)]

    def _read(self, path: PurePosixPath) -> str:
        try:
            return self._repo.git("show", f"{self.sha()}:{path}").stdout
        except GitError as exc:
            msg = str(exc)
            if "does not exist in" in msg or "exists on disk, but not" in msg:
                raise FileNotFoundError(f"{path} does not exist")
            raise

    def _write(self, path: PurePosixPath, contents: str) -> None:
        # Update the index without touching the worktree.
        # https://stackoverflow.com/a/25352119
        with tempfile.NamedTemporaryFile(delete_on_close=False) as temp:
            temp.write(contents.encode("utf8"))
            temp.close()
            self._write_from_disk(path, Path(temp.name))

    def _write_from_disk(
        self, path: PurePosixPath, contents_path: Path
    ) -> None:
        blob_sha = self._repo.git(
            "hash-object",
            "-w",
            "--path",
            str(path),
            str(contents_path),
        ).stdout
        self._updates.append(_WriteBlob(path, blob_sha))

    def _delete(self, path: PurePosixPath) -> None:
        self._updates.append(_DeleteBlob(path))

    @contextlib.contextmanager
    def _edit(self) -> Iterator[Path]:
        commit_sha = self._repo.git(
            "commit-tree", "-m", "draft! worktree", self.sha()
        ).stdout
        with tempfile.TemporaryDirectory() as path_str:
            try:
                self._repo.git(
                    "worktree", "add", "--detach", path_str, commit_sha
                )
                path = Path(path_str)
                yield path
                self._sync_updates(worktree_path=path)
            finally:
                self._repo.git("worktree", "remove", "-f", path_str)


class _Update:
    """Generic tree update"""


@dataclasses.dataclass(frozen=True)
class _WriteBlob(_Update):
    path: PurePosixPath
    blob_sha: SHA


@dataclasses.dataclass(frozen=True)
class _DeleteBlob(_Update):
    path: PurePosixPath


def _update_tree(sha: SHA, updates: Sequence[_Update], repo: Repo) -> SHA:
    if not updates:
        return sha

    blob_shas = collections.defaultdict[PurePosixPath, dict[str, str]](dict)
    trees = collections.defaultdict[PurePosixPath, set[str]](set)
    for update in updates:
        match update:
            case _WriteBlob(path, blob_sha):
                blob_shas[path.parent][path.name] = blob_sha
                for parent in path.parents[:-1]:
                    trees[parent.parent].add(parent.name)
            case _DeleteBlob(path):
                blob_shas[path.parent][path.name] = ""
            case _:
                raise UnreachableError(f"Unexpected update: {update}")

    def visit_old_tree(sha: SHA, path: PurePosixPath) -> SHA:
        old_lines = null_delimited(repo.git("ls-tree", "-z", sha).stdout)
        new_blob_shas = blob_shas.pop(path, dict())
        new_trees = trees.pop(path, set())

        new_lines = list[str]()
        for line in old_lines:
            old_prefix, name = line.split("\t", 1)
            mode, otype, old_sha = old_prefix.split(" ")
            match otype:
                case "blob":
                    if name in new_trees:
                        raise RuntimeError(f"Not a folder: {path / name}")
                    new_sha = new_blob_shas.pop(name, old_sha)
                    if new_sha:
                        new_lines.append(f"{mode} blob {new_sha}\t{name}")
                case "tree":
                    new_trees.discard(name)
                    new_sha = visit_old_tree(old_sha, path / name)
                    new_lines.append(f"040000 tree {new_sha}\t{name}")
                case "commit":  # Submodule
                    new_lines.append(line)
                case _:
                    raise UnreachableError(f"Unexpected line: {line}")

        for name in new_trees:
            sha = visit_new_tree(path / name)
            new_lines.append(f"040000 tree {sha}\t{name}")
        for name, blob_sha in new_blob_shas.items():
            if blob_sha:
                new_lines.append(f"100644 blob {blob_sha}\t{name}")
            else:
                _logger.warning("Unmatched deletion. [path=%s]", path / name)

        if new_lines == old_lines:
            return sha

        return repo.git("mktree", "-z", stdin="\x00".join(new_lines)).stdout

    def visit_new_tree(path: PurePosixPath) -> SHA:
        lines = list[str]()
        for name in trees.pop(path, set()):
            tree_sha = visit_new_tree(path / name)
            lines.append(f"040000 tree {tree_sha}\t{name}")
        for name, blob_sha in blob_shas.pop(path, dict()).items():
            lines.append(f"100644 blob {blob_sha}\t{name}")
        return repo.git("mktree", "-z", stdin="\x00".join(lines)).stdout

    new_sha = visit_old_tree(sha, PurePosixPath("."))
    assert not blob_shas, "unprocessed blobs"
    assert not trees, "unprocessed trees"
    return new_sha
