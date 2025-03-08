"""Prompt templating support"""

import dataclasses
import os
import os.path as osp
from typing import Mapping, Self, Sequence

import jinja2

from .bots import Toolbox
from .common import Config, package_root


_prompt_root = package_root / "prompts"


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


class PromptRenderer:
    """Renderer for prompt templates using Jinja2"""

    def __init__(self, env: jinja2.Environment) -> None:
        self._environment = env

    @classmethod
    def for_toolbox(cls, toolbox: Toolbox) -> Self:
        env = _jinja_environment()
        env.globals["repo"] = {
            "file_paths": [str(p) for p in toolbox.list_files()],
        }
        return cls(env)

    def render(self, prompt: TemplatedPrompt) -> str:
        template = self._environment.get_template(f"{prompt.template}.jinja")
        return template.render(prompt.context)


def list_templates() -> Sequence[str]:
    return [
        osp.splitext(name)[0]
        for name in _jinja_environment().list_templates(extensions=["jinja"])
        if not any(p.startswith(".") for p in name.split(os.sep))
    ]


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
