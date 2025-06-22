"""Prompt templating support"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
import enum
import functools
import os
from pathlib import Path
import re
from typing import Self, TypedDict, cast

import docopt
import jinja2

from .common import Config, Table, package_root
from .toolbox import NoopToolbox, Toolbox


_extension = "jinja"


type PromptName = str


@dataclasses.dataclass(frozen=True)
class TemplatedPrompt:
    """A parameterized prompt"""

    name: PromptName
    args: tuple[str, ...] = ()

    @classmethod
    def public(cls, name: PromptName, args: Sequence[str]) -> Self:
        _check_public_template_name(name)
        return cls(name, tuple(args))

    def render(self, toolbox: Toolbox) -> str:
        prompt = _load_prompt(_jinja_environment(), self.name, toolbox)
        return prompt.render(self.args)


_public_template_name_pattern = re.compile(r"\.?[a-z-]+")


def _check_public_template_name(name: str) -> None:
    if not _public_template_name_pattern.fullmatch(name):
        raise ValueError(f"Invalid template name: {name}")


def _jinja_environment(*, include_local: bool = True) -> jinja2.Environment:
    folders = [_PromptFolder.BUILTIN]
    if include_local:
        folders.append(_PromptFolder.LOCAL)
    return jinja2.Environment(
        auto_reload=False,
        autoescape=False,
        keep_trailing_newline=True,
        loader=jinja2.FileSystemLoader([f.path for f in folders]),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=jinja2.StrictUndefined,
    )


class _PromptFolder(enum.Enum):
    BUILTIN = package_root
    LOCAL = Config.folder_path()

    @property
    def path(self) -> Path:
        return self.value / "prompts"


@functools.cache
def _load_layouts() -> Mapping[str, str]:
    root = _PromptFolder.BUILTIN.path
    return {
        p.stem: str(p.relative_to(root))
        for p in (root / ".LAYOUTS").glob(f"*.{_extension}")
    }


class _Context(TypedDict):
    prompt: Mapping[str, str]
    program: PromptName
    toolbox: Toolbox


@dataclasses.dataclass(frozen=True)
class PromptMetadata:
    """Metadata about an available template"""

    rel_path: Path
    abs_path: Path
    description: str | None = None

    @property
    def name(self) -> str:
        return str(self.rel_path.parent / self.rel_path.stem)

    def source(self) -> str:
        with self.abs_path.open() as reader:
            return reader.read()

    def is_local(self) -> bool:
        return not self.abs_path.is_relative_to(_PromptFolder.BUILTIN.path)

    def local_path(self) -> Path:
        if self.is_local():
            return self.abs_path
        return _PromptFolder.LOCAL.path / self.rel_path

    @staticmethod
    def local_path_for(name: str) -> Path:
        _check_public_template_name(name)
        return _PromptFolder.LOCAL.path / Path(f"{name}.{_extension}")


class _Prompt:
    """Instantiated dynamic prompt"""

    def __init__(self, metadata: PromptMetadata) -> None:
        self.metadata = metadata

    def render(self, args: Sequence[str]) -> str:
        raise NotImplementedError()


class _StandalonePrompt(_Prompt):
    """Prompt without a layout"""

    def __init__(self, metadata: PromptMetadata, rendered: str) -> None:
        super().__init__(metadata)
        self._rendered = rendered

    def render(self, args: Sequence[str]) -> str:
        if args:
            raise RuntimeError("Arguments not supported for this template")
        return self._rendered


class _DocoptPrompt(_Prompt):
    """Prompt which supports options via docopt"""

    def __init__(
        self,
        template: jinja2.Template,
        doc: str,
        rel_path: Path,
        context: _Context,
    ) -> None:
        # We could validate the doc string here, but don't since docopt doesn't
        # make it easy with inline print and sys.exit calls.
        super().__init__(
            PromptMetadata(
                rel_path,
                _template_path(template),
                doc.partition("\n")[0],
            )
        )
        self._template = template
        self._doc = doc
        self._context = context

    def render(self, args: Sequence[str]) -> str:
        try:
            opts = docopt.docopt(self._doc, list(args))
        except docopt.DocoptExit as exc:
            raise ValueError(f"Invalid template arguments\n{exc}") from exc
        return self._template.render({**self._context, "opts": opts})


def _template_path(template: jinja2.Template) -> Path:
    """Returns the template's absolute path"""
    assert template.filename
    path = Path(template.filename)
    assert path.is_absolute()
    return path


def _load_prompt(
    env: jinja2.Environment, name: PromptName, toolbox: Toolbox
) -> _Prompt:
    rel_path = Path(f"{name}.{_extension}")
    assert env.loader, "No loader in environment"
    template = env.loader.load(env, str(rel_path))
    context: _Context = dict(
        program=name, prompt=_load_layouts(), toolbox=toolbox
    )
    try:
        module = template.make_module(vars=cast(dict, context))
    except jinja2.TemplateError as exc:
        raise ValueError(f"Template {name} is invalid: {exc}") from exc
    match getattr(module, "layout", None):
        case "docopt":
            return _DocoptPrompt(template, str(module), rel_path, context)
        case _:
            metadata = PromptMetadata(rel_path, _template_path(template))
            return _StandalonePrompt(metadata, str(module))


def find_prompt_metadata(name: PromptName) -> PromptMetadata | None:
    try:
        prompt = _load_prompt(_jinja_environment(), name, NoopToolbox())
    except jinja2.TemplateNotFound:
        return None
    return prompt.metadata


def templates_table(*, include_local: bool = True) -> Table:
    env = _jinja_environment(include_local=include_local)
    toolbox = NoopToolbox()
    table = Table.empty()
    table.data.field_names = ["name", "local", "description"]
    for rel_path in env.list_templates(extensions=[_extension]):
        if any(p.startswith(".") for p in rel_path.split(os.sep)):
            continue
        name, _ext = os.path.splitext(rel_path)
        prompt = _load_prompt(env, name, toolbox)
        metadata = prompt.metadata
        local = "y" if metadata.is_local() else "n"
        table.data.add_row([name, local, metadata.description or ""])
    return table
