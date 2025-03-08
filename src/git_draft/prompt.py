"""Prompt templating support"""

import dataclasses
import enum
import itertools
import os
import os.path as osp
from typing import Mapping, Self

import jinja2
import jinja2.meta

from .bots import Toolbox
from .common import Config, Table, package_root


_prompt_root = package_root / "prompts"


_extension = "jinja"


@dataclasses.dataclass(frozen=True)
class TemplatedPrompt:
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


class _Global(enum.StrEnum):
    REPO = enum.auto()


class PromptRenderer:
    """Renderer for prompt templates using Jinja2"""

    def __init__(self, env: jinja2.Environment) -> None:
        self._environment = env

    @classmethod
    def for_toolbox(cls, toolbox: Toolbox) -> Self:
        env = _jinja_environment()
        env.globals[_Global.REPO] = {
            "file_paths": [str(p) for p in toolbox.list_files()],
        }
        return cls(env)

    def render(self, prompt: TemplatedPrompt) -> str:
        tpl = self._environment.get_template(f"{prompt.template}.{_extension}")
        return tpl.render(prompt.context)


def templates_table() -> Table:
    env = _jinja_environment()
    table = Table.empty()
    table.data.field_names = ["name", "local", "preamble"]
    for rel_path in env.list_templates(extensions=[_extension]):
        if any(p.startswith(".") for p in rel_path.split(os.sep)):
            continue
        tpl = _Template.create(rel_path, env)
        local = "y" if tpl.is_local else "n"
        table.data.add_row([tpl.name, local, tpl.preamble or "-"])
    return table


def template_source(name: str) -> str:
    env = _jinja_environment()
    try:
        tpl = _Template.create(f"{name}.{_extension}", env)
    except jinja2.TemplateNotFound:
        raise ValueError(f"No template named {name!r}")
    return tpl.source


@dataclasses.dataclass(frozen=True)
class _Template:
    rel_path: str
    abs_path: str | None
    source: str
    preamble: str | None

    @property
    def name(self) -> str:
        return osp.splitext(self.rel_path)[0]

    @property
    def is_local(self) -> bool:
        if not self.abs_path:
            return False
        return str(_prompt_root) not in self.abs_path

    def extract_variables(self, env: jinja2.Environment) -> frozenset[str]:
        """Returns the names of variables directly used in the template

        The returned set does not include transitive variables (used in
        included templates) or variables populated automatically (e.g. `repo`).
        """
        # https://stackoverflow.com/a/48685520
        ast = env.parse(self.source)
        return frozenset(jinja2.meta.find_undeclared_variables(ast))

    @classmethod
    def create(cls, rel_path: str, env: jinja2.Environment) -> Self:
        assert env.loader, "No loader in environment"
        source, abs_path, _uptodate = env.loader.get_source(env, rel_path)
        preamble = cls._extract_preamble(source, env)
        return cls(rel_path, abs_path, source, preamble)

    @staticmethod
    def _extract_preamble(source: str, env: jinja2.Environment) -> str | None:
        """Returns the template's leading comment's contents, if preset"""
        tokens = list(itertools.islice(env.lex(source), 3))
        if len(tokens) == 3 and tokens[1][1] == "comment":
            return tokens[1][2].strip()
        return None


def _jinja_environment() -> jinja2.Environment:
    return jinja2.Environment(
        auto_reload=False,
        autoescape=False,
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader(
            [Config.folder_path() / "prompts", str(_prompt_root)]
        ),
        undefined=jinja2.StrictUndefined,
    )
