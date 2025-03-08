"""CLI entry point"""

from __future__ import annotations

import importlib.metadata
import logging
import optparse
from pathlib import PurePosixPath
import sys
from typing import Sequence

from .bots import load_bot
from .common import PROGRAM, Config, UnreachableError, ensure_state_home
from .drafter import Drafter
from .editor import open_editor
from .prompt import TemplatedPrompt, template_source, templates_table
from .store import Store
from .toolbox import ToolVisitor


_logger = logging.getLogger(__name__)


def new_parser() -> optparse.OptionParser:
    parser = optparse.OptionParser(
        prog=PROGRAM,
        version=importlib.metadata.version("git_draft"),
    )

    parser.disable_interspersed_args()

    parser.add_option(
        "--log",
        help="show log path and exit",
        action="store_true",
    )
    parser.add_option(
        "--root",
        help="path used to locate repository root",
        dest="root",
    )

    def add_command(name: str, short: str | None = None, **kwargs) -> None:
        def callback(_option, _opt, _value, parser) -> None:
            parser.values.command = name

        parser.add_option(
            f"-{short or name[0].upper()}",
            f"--{name}",
            action="callback",
            callback=callback,
            **kwargs,
        )

    add_command("finalize", help="apply current draft to original branch")
    add_command("generate", help="start a new draft from a prompt")
    add_command("history", help="show history drafts or prompts")
    add_command("revert", help="discard the current draft")
    add_command("templates", help="show template information")

    parser.add_option(
        "-b",
        "--bot",
        dest="bot",
        help="bot name",
    )
    parser.add_option(
        "-c",
        "--clean",
        help="remove deleted files from work directory",
        action="store_true",
    )
    parser.add_option(
        "-d",
        "--delete",
        help="delete draft after finalizing or discarding",
        action="store_true",
    )
    # TODO: Add edit option. Works both for prompts and templates.
    parser.add_option(
        "-j",
        "--json",
        help="use JSON for table output",
        action="store_true",
    )
    parser.add_option(
        "-r",
        "--reset",
        help="reset index before generating a new draft",
        action="store_true",
    )
    parser.add_option(
        "-s",
        "--sync",
        help="commit prior worktree changes separately",
        action="store_true",
    )
    parser.add_option(
        "-t",
        "--timeout",
        dest="timeout",
        help="bot generation timeout",
    )

    return parser


class ToolPrinter(ToolVisitor):
    def on_list_files(
        self, _paths: Sequence[PurePosixPath], _reason: str | None
    ) -> None:
        print("Listing available files...")

    def on_read_file(
        self, path: PurePosixPath, _contents: str | None, _reason: str | None
    ) -> None:
        print(f"Reading {path}...")

    def on_write_file(
        self, path: PurePosixPath, _contents: str, _reason: str | None
    ) -> None:
        print(f"Updated {path}.")

    def on_delete_file(self, path: PurePosixPath, _reason: str | None) -> None:
        print(f"Deleted {path}.")


def main() -> None:
    config = Config.load()
    (opts, args) = new_parser().parse_args()

    log_path = ensure_state_home() / "log"
    if opts.log:
        print(log_path)
        return
    logging.basicConfig(level=config.log_level, filename=str(log_path))

    drafter = Drafter.create(store=Store.persistent(), path=opts.root)
    command = getattr(opts, "command", "generate")
    if command == "generate":
        bot_config = None
        if opts.bot:
            bot_configs = [c for c in config.bots if c.name == opts.bot]
            if len(bot_configs) != 1:
                raise ValueError(f"Found {len(bot_configs)} matching bots")
            bot_config = bot_configs[0]
        elif config.bots:
            bot_config = config.bots[0]
        bot = load_bot(bot_config)

        prompt: str | TemplatedPrompt
        if args:
            prompt = TemplatedPrompt.parse(args[0], *args[1:])
        else:
            if sys.stdin.isatty():
                prompt = open_editor("Enter your prompt here...")
            else:
                prompt = sys.stdin.read()

        name = drafter.generate_draft(
            prompt,
            bot,
            bot_name=opts.bot,
            tool_visitors=[ToolPrinter()],
            reset=opts.reset,
        )
        print(f"Generated {name}.")
    elif command == "finalize":
        name = drafter.finalize_draft(clean=opts.clean, delete=opts.delete)
        print(f"Finalized {name}.")
    elif command == "revert":
        name = drafter.revert_draft(delete=opts.delete)
        print(f"Reverted {name}.")
    elif command == "history":
        table = drafter.history_table(args[0] if args else None)
        if table:
            print(table.to_json() if opts.json else table)
    elif command == "templates":
        if args:
            print(template_source(args[0]))
        else:
            table = templates_table()
            print(table.to_json() if opts.json else table)
    else:
        raise UnreachableError()


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        _logger.exception("Program failed.")
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
