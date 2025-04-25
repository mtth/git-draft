"""CLI entry point"""

from __future__ import annotations

import enum
import importlib.metadata
import logging
import optparse
from pathlib import Path
import sys

from .bots import load_bot
from .common import (
    PROGRAM,
    Config,
    Feedback,
    UnreachableError,
    ensure_state_home,
)
from .drafter import Drafter, DraftMergeStrategy
from .editor import open_editor
from .git import Repo
from .prompt import Template, TemplatedPrompt, find_template, templates_table
from .store import Store


_logger = logging.getLogger(__name__)


def new_parser() -> optparse.OptionParser:
    parser = optparse.OptionParser(
        prog=PROGRAM,
        version=importlib.metadata.version("git_draft"),
    )

    parser.disable_interspersed_args()

    parser.add_option(
        "--log-path",
        help="show log path and exit",
        action="store_true",
    )
    parser.add_option(
        "--root",
        help="path used to locate repository root",
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
    add_command("templates", short="T", help="show template information")

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
        "-j",
        "--json",
        help="use JSON for table output",
        action="store_true",
    )

    parser.add_option(
        "--no-accept",
        help="do not merge draft",
        dest="accept",
        action="store_const",
        const=0,
    )

    return parser


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


def edit(*, path: Path | None = None, text: str | None = None) -> str:
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


_PROMPT_PLACEHOLDER = "Enter your prompt here..."


def main() -> None:  # noqa: PLR0912 PLR0915
    config = Config.load()
    (opts, args) = new_parser().parse_args()

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

    feedback = Feedback.dynamic() if sys.stdin.isatty() else Feedback.static()
    repo = Repo.enclosing(Path(opts.root) if opts.root else Path.cwd())
    drafter = Drafter.create(repo, Store.persistent(), feedback)
    match getattr(opts, "command", "new"):
        case "new":
            bot_config = None
            bot_name = opts.bot or repo.default_bot()
            if bot_name:
                bot_configs = [c for c in config.bots if c.name == opts.bot]
                if len(bot_configs) != 1:
                    raise ValueError(f"Found {len(bot_configs)} matching bots")
                bot_config = bot_configs[0]
            elif config.bots:
                bot_config = config.bots[0]
            bot = load_bot(bot_config)

            prompt: str | TemplatedPrompt
            editable = opts.edit
            if args:
                prompt = TemplatedPrompt.parse(args[0], *args[1:])
            elif opts.edit:
                editable = False
                prompt = edit(
                    text=drafter.latest_draft_prompt() or _PROMPT_PLACEHOLDER
                ).strip()
                if not prompt or prompt == _PROMPT_PLACEHOLDER:
                    raise ValueError("Aborting: empty or placeholder prompt")
            else:
                if sys.stdin.isatty():
                    print("Reading prompt from stdin... (press C-D when done)")
                prompt = sys.stdin.read()

            accept = Accept(opts.accept or 0)
            _ = drafter.generate_draft(
                prompt,
                bot,
                prompt_transform=open_editor if editable else None,
                merge_strategy=accept.merge_strategy(),
            )
        case "quit":
            drafter.quit_folio()
        case "templates":
            if args:
                name = args[0]
                tpl = find_template(name)
                if opts.edit:
                    if tpl:
                        edit(path=tpl.local_path(), text=tpl.source)
                    else:
                        edit(path=Template.local_path_for(name))
                else:
                    if not tpl:
                        raise ValueError(f"No template named {name!r}")
                    print(tpl.source)
            else:
                table = templates_table()
                print(table.to_json() if opts.json else table)
        case _:
            raise UnreachableError()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        _logger.exception("Program failed.")
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
