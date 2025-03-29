"""Prompt templating support"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
import enum
import itertools
import os
from pathlib import Path
from typing import Self

import jinja2
import jinja2.meta

from .bots import Toolbox
from .common import Config, Table, package_root


_extension = "jinja"


@dataclasses.dataclass(frozen=True)
class TemplatedPrompt:
    """A parametrized prompt"""

    template: str
    context: Mapping[str, str]

    @classmethod
    def parse(cls, name: str, *args: str) -> Self:
        """Parse arguments into a TemplatedPrompt

        Args:
            name: The name of the template.
            *args: Additional arguments for context, expected in 'key=value'
                format.

        """
        return cls(name, dict(e.split("=", 1) for e in args))


class _GlobalVariable(enum.StrEnum):
    REPO = enum.auto()


class PromptRenderer:
    """Renderer for prompt templates using Jinja2"""

    def __init__(self, env: jinja2.Environment) -> None:
        self._environment = env

    @classmethod
    def for_toolbox(cls, toolbox: Toolbox) -> Self:
        env = _jinja_environment()
        env.globals[_GlobalVariable.REPO] = {
            "file_paths": [str(p) for p in toolbox.list_files()],
        }
        return cls(env)

    def render(self, prompt: TemplatedPrompt) -> str:
        tpl = self._environment.get_template(f"{prompt.template}.{_extension}")
        try:
            return tpl.render(prompt.context)
        except jinja2.UndefinedError as err:
            raise ValueError(f"Unable to render template: {err}")


def templates_table() -> Table:
    env = _jinja_environment()
    table = Table.empty()
    table.data.field_names = ["name", "local", "preamble"]
    for rel_path in env.list_templates(extensions=[_extension]):
        if any(p.startswith(".") for p in rel_path.split(os.sep)):
            continue
        tpl = _load_template(rel_path, env)
        local = "y" if tpl.is_local() else "n"
        table.data.add_row([tpl.name, local, tpl.preamble or "-"])
    return table


class _PromptFolder(enum.Enum):
    BUILTIN = package_root / "prompts"
    LOCAL = Config.folder_path() / "prompts"

    @property
    def path(self) -> Path:
        return self.value


def _extract_preamble(source: str, env: jinja2.Environment) -> str | None:
    """Returns the template's leading comment's contents, if preset"""
    tokens = list(itertools.islice(env.lex(source), 3))
    if len(tokens) == 3 and tokens[1][1] == "comment":
        return tokens[1][2].strip()
    return None


def _load_template(rel_path: str, env: jinja2.Environment) -> Template:
    assert env.loader, "No loader in environment"
    source, abs_path, _uptodate = env.loader.get_source(env, rel_path)
    assert abs_path, "Missing template path"
    preamble = _extract_preamble(source, env)
    return Template(Path(rel_path), Path(abs_path), source, preamble)


def find_template(name: str) -> Template | None:
    env = _jinja_environment()
    try:
        return _load_template(f"{name}.{_extension}", env)
    except jinja2.TemplateNotFound:
        return None


@dataclasses.dataclass(frozen=True)
class Template:
    """An available template"""

    rel_path: Path
    abs_path: Path
    source: str
    preamble: str | None

    @property
    def name(self) -> str:
        return str(self.rel_path.parent / self.rel_path.stem)

    def is_local(self) -> bool:
        return not self.abs_path.is_relative_to(_PromptFolder.BUILTIN.path)

    def local_path(self) -> Path:
        if self.is_local():
            return self.abs_path
        return _PromptFolder.LOCAL.path / self.rel_path

    def extract_variables(self, env: jinja2.Environment) -> frozenset[str]:
        """Returns the names of variables directly used in the template

        The returned set does not include transitive variables (used in
        included templates) or variables populated automatically (e.g. `repo`).
        """
        # https://stackoverflow.com/a/48685520
        ast = env.parse(self.source)
        return frozenset(jinja2.meta.find_undeclared_variables(ast))

    @staticmethod
    def local_path_for(name: str) -> Path:
        return _PromptFolder.LOCAL.path / Path(f"{name}.{_extension}")


def _jinja_environment() -> jinja2.Environment:
    return jinja2.Environment(
        auto_reload=False,
        autoescape=False,
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader([p.path for p in _PromptFolder]),
        undefined=jinja2.StrictUndefined,
    )
