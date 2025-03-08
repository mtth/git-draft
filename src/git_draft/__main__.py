"""CLI entry point"""

from __future__ import annotations

import importlib.metadata
import logging
import optparse
from pathlib import Path, PurePosixPath
import sys
from typing import Sequence

from .bots import load_bot
from .common import PROGRAM, Config, UnreachableError, ensure_state_home
from .drafter import Drafter
from .editor import open_editor
from .prompt import Template, TemplatedPrompt, templates_table
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
    add_command("show-drafts", short="D", help="show draft history")
    add_command("show-prompts", short="P", help="show prompt history")
    add_command("show-templates", short="T", help="show template information")

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
        "-r",
        "--revert",
        help="abandon any changes since draft creation",
        action="store_true",
    )
    parser.add_option(
        "-s",
        "--sync",
        help="commit prior worktree changes separately",
        action="store_true",
    )

    parser.add_option(
        "--no-reset",
        help="abort if there are any staged changes",
        dest="reset",
        action="store_false",
    )
    parser.add_option(
        "--reset",
        help="reset index before generating a new draft",
        dest="reset",
        action="store_true",
    )
    parser.add_option(
        "--timeout",
        dest="timeout",
        help="generation timeout",
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


def edit(text: str | None, path: Path | None) -> str | None:
    if sys.stdin.isatty():
        return open_editor(text or "", path)
    else:
        if path and text is not None:
            with open(path, "w") as f:
                f.write(text)
        print(path)
        return None


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
            reset=config.auto_reset if opts.reset is None else opts.reset,
            sync=opts.sync,
        )
        print(f"Generated {name}.")
    elif command == "finalize":
        name = drafter.exit_draft(
            revert=opts.revert, clean=opts.clean, delete=opts.delete
        )
        verb = "Reverted" if opts.revert else "Finalized"
        print(f"{verb} {name}.")
    elif command == "show-drafts":
        table = drafter.history_table(args[0] if args else None)
        if table:
            print(table.to_json() if opts.json else table)
    elif command == "show-prompts":
        raise NotImplementedError()  # TODO
    elif command == "show-templates":
        if args:
            name = args[0]
            tpl = Template.find(name)
            if opts.edit:
                if tpl:
                    edit(tpl.source, tpl.local_path())
                else:
                    edit("", Template.local_path_for(name))
            else:
                if not tpl:
                    raise ValueError(f"No template named {name!r}")
                print(tpl.source)
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
