from __future__ import annotations

import importlib.metadata
import logging
import optparse
import sys

from .bots import Operation, load_bot
from .common import Config, PROGRAM, Store, ensure_state_home, open_editor
from .manager import Manager


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
        help="path used to locate repository",
        dest="root",
    )

    def add_command(name: str, **kwargs) -> None:
        def callback(_option, _opt, _value, parser) -> None:
            parser.values.command = name

        parser.add_option(
            f"-{name[0].upper()}",
            f"--{name}",
            action="callback",
            callback=callback,
            **kwargs,
        )

    add_command("discard", help="discard the current draft")
    add_command("finalize", help="apply current draft to original branch")
    add_command("generate", help="start a new draft from a prompt")

    parser.add_option(
        "-b",
        "--bot",
        dest="bot",
        help="bot key",
        default="openai",
    )
    parser.add_option(
        "-c",
        "--checkout",
        help="check out generated changes",
        action="store_true",
    )
    parser.add_option(
        "-d",
        "--delete",
        help="delete draft after finalizing or discarding",
        action="store_true",
    )
    parser.add_option(
        "-p",
        "--prompt",
        dest="prompt",
        help="draft generation prompt, read from stdin if unset",
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

    return parser


def print_operation(op: Operation) -> None:
    print(op)


def main() -> None:
    config = Config.load()
    (opts, _args) = new_parser().parse_args()

    log_path = ensure_state_home() / "log"
    if opts.log:
        print(log_path)
        return
    logging.basicConfig(level=config.log_level, filename=str(log_path))

    manager = Manager.create(
        store=Store.persistent(),
        path=opts.root,
        operation_hook=print_operation,
    )
    command = getattr(opts, "command", "generate")
    if command == "generate":
        bot = load_bot(opts.bot, {})
        prompt = opts.prompt
        if not prompt:
            if sys.stdin.isatty():
                prompt = open_editor("Enter your prompt here...")
            else:
                prompt = sys.stdin.read()
        manager.generate_draft(
            prompt, bot, checkout=opts.checkout, reset=opts.reset
        )
    elif command == "finalize":
        manager.finalize_draft(delete=opts.delete)
    elif command == "discard":
        manager.discard_draft(delete=opts.delete)
    else:
        assert False, "unreachable"


if __name__ == "__main__":
    main()
