"""CLI entry point"""

from __future__ import annotations

import asyncio
import dataclasses
import enum
import importlib.metadata
import logging
import optparse
from pathlib import Path
import sys
from typing import Any

from .bots import load_bot
from .common import PROGRAM, Config, UnreachableError, ensure_state_home
from .drafter import Drafter, DraftMergeStrategy
from .editor import open_editor
from .git import Repo
from .progress import Progress
from .prompt import (
    PromptMetadata,
    TemplatedPrompt,
    find_prompt_metadata,
    list_templates,
)
from .store import Store


_logger = logging.getLogger(__name__)


class Accept(enum.Enum):
    """Valid change accept mode"""

    MANUAL = 0
    MERGE = enum.auto()
    MERGE_THEIRS = enum.auto()
    MERGE_THEN_QUIT = enum.auto()

    def merge_strategy(self) -> DraftMergeStrategy | None:
        match self:
            case Accept.MANUAL:
                return None
            case Accept.MERGE:
                return "ignore-all-space"
            case Accept.MERGE_THEIRS | Accept.MERGE_THEN_QUIT:
                return "theirs"
            case _:
                raise UnreachableError()


def _new_parser() -> optparse.OptionParser:
    parser = optparse.OptionParser(
        prog=PROGRAM,
        version=importlib.metadata.version("git_draft"),
    )

    parser.disable_interspersed_args()

    parser.add_option(
        "--batch",
        help="disable interactive feedback",
        action="store_true",
    )
    parser.add_option(
        "--log-path",
        help="show log path and exit",
        action="store_true",
    )
    parser.add_option(
        "--root",
        help=optparse.SUPPRESS_HELP,  # Not needed when invoked via git
        dest="root",
    )

    def add_command(name: str, short: str | None = None, **kwargs) -> None:
        def callback(
            _option: object,
            _opt: object,
            _value: object,
            parser: optparse.OptionParser,
        ) -> None:
            assert parser.values
            parser.values.command = name

        parser.add_option(
            f"-{short or name[0].upper()}",
            f"--{name}",
            action="callback",
            callback=callback,
            **kwargs,
        )

    add_command("new", help="create a new draft from a prompt")
    add_command("quit", help="return to original branch")
    add_command("list-events", short="E", help="list events")
    add_command("show-template", short="S", help="show template information")
    add_command("list-templates", short="T", help="list available templates")

    parser.add_option(
        "-a",
        "--accept",
        help="merge draft, may be repeated",
        action="count",
    )
    parser.add_option(
        "-b",
        "--bot",
        dest="bot",
        help="AI bot name",
    )
    parser.add_option(
        "-e",
        "--edit",
        help="edit prompt or template",
        action="store_true",
    )
    parser.add_option(
        "--no-accept",
        help="do not merge draft",
        dest="accept",
        action="store_const",
        const=0,
    )
    parser.add_option(
        "-f",
        "--format",
        dest="format",
        help="formatting string",
    )

    return parser


def _edit(*, path: Path | None = None, text: str | None = None) -> str:
    if sys.stdin.isatty():
        return open_editor(text or "", path)
    # We exit with a custom code to allow the caller to act accordingly.
    # For example we can handle this from Vim by opening the returned path
    # or text in a buffer, to then continue to another command on save.
    # https://unix.stackexchange.com/q/604260
    elif path is None:
        assert text, "Empty path and text"
        print(text)
        sys.exit(198)
    else:
        if text is not None:
            with open(path, "w") as f:
                f.write(text)
        print(path)
        sys.exit(199)


def _format(props: Any, spec: str) -> str:
    """Formats an instance of a dataclass using the provided pattern"""
    return spec.format(**dataclasses.asdict(props))


_PROMPT_PLACEHOLDER = "Enter your prompt here..."


async def run() -> None:  # noqa: PLR0912 PLR0915
    config = Config.load()
    (opts, args) = _new_parser().parse_args()

    log_path = ensure_state_home() / "log"
    if opts.log_path:
        print(log_path)
        return
    logging.basicConfig(
        level=config.log_level,
        filename=str(log_path),
        format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        datefmt="%m-%d %H:%M",
    )

    progress = (
        Progress.dynamic()
        if sys.stdin.isatty() and not opts.batch
        else Progress.static()
    )
    repo = Repo.enclosing(Path(opts.root) if opts.root else Path.cwd())
    drafter = Drafter.create(repo, Store.persistent(), progress)
    match getattr(opts, "command", "new"):
        case "new":
            bot_config = None
            bot_name = opts.bot or repo.default_bot()
            if bot_name:
                bot_configs = [c for c in config.bots if c.name == bot_name]
                if len(bot_configs) != 1:
                    raise ValueError(f"Found {len(bot_configs)} matching bots")
                bot_config = bot_configs[0]
            elif config.bots:
                bot_config = config.bots[0]
            bot = load_bot(bot_config)

            prompt: str | TemplatedPrompt
            if args:
                if args[0] == "-":
                    prompt = sys.stdin.read()
                else:
                    prompt = TemplatedPrompt.public(args[0], args[1:])
                editable = opts.edit
            else:
                prompt = _edit(
                    text=drafter.latest_draft_prompt() or _PROMPT_PLACEHOLDER
                ).strip()
                if prompt.strip() == _PROMPT_PLACEHOLDER:
                    prompt = ""  # Enable consistent error message
                editable = False  # We already edited the prompt

            accept = Accept(opts.accept or 0)
            await drafter.generate_draft(
                prompt=prompt,
                bot=bot,
                merge_strategy=accept.merge_strategy(),
                prompt_transform=open_editor if editable else None,
            )
            if accept == Accept.MERGE_THEN_QUIT:
                # TODO: Refuse to quit on pending question?
                drafter.quit_folio()
        case "quit":
            drafter.quit_folio()
        case "list-events":
            draft_id = args[0] if args else None
            spec = opts.format or "{occurred_at}\t{description}"
            for props in drafter.list_draft_events(draft_id):
                print(_format(props, spec))
        case "show-template":
            if len(args) != 1:
                raise ValueError("Expected exactly one argument")
            name = args[0]
            meta = find_prompt_metadata(name)
            if opts.edit:
                if meta:
                    _edit(path=meta.local_path(), text=meta.source())
                else:
                    _edit(path=PromptMetadata.local_path_for(name))
            else:
                if not meta:
                    raise ValueError(f"No template named {name!r}")
                print(meta.source())
        case "list-templates":
            spec = opts.format or "{name}: {description}"
            for props in list_templates():
                print(_format(props, spec))
        case _:
            raise UnreachableError()


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as err:
        _logger.exception("Program failed.")
        message = str(err) or "See logs for more information"
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
