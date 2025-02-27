from pathlib import PurePosixPath
from typing import Protocol, Sequence


class Toolbox(Protocol):
    def list_files(self) -> Sequence[PurePosixPath]: ...
    def read_file(self, path: PurePosixPath) -> str: ...
    def write_file(self, path: PurePosixPath, data: str) -> None: ...


class Backend:
    def run(self, toolbox: Toolbox) -> None: ...


class NewFileBackend(Backend):
    def run(self, toolbox: Toolbox) -> None:
        # send request to backend...
        import time

        time.sleep(2)

        # Add files to index.
        import random

        name = f"foo-{random.randint(1, 100)}"
        toolbox.write_file(PurePosixPath(name), "hello!\n")
