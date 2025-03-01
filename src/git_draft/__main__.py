from __future__ import annotations

import importlib.metadata
import optparse
import sys
import textwrap

from . import Manager, OpenAIAssistant, enclosing_repo, open_editor


EPILOG = """\
    More information via `man git-draft` and https://mtth.github.io/git-draft.
"""


parser = optparse.OptionParser(
    prog="git-draft",
    epilog=textwrap.dedent(EPILOG),
    version=importlib.metadata.version("git_draft"),
)

parser.disable_interspersed_args()


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


add_command("discard", help="discard all drafts associated with a branch")
add_command("finalize", help="apply the current draft to the original branch")
add_command("generate", help="draft a new change from a prompt")

parser.add_option(
    "-d",
    "--delete",
    help="delete the draft after finalizing or discarding",
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


EDITOR_PLACEHOLDER = """\
    Enter your prompt here...
"""


def main() -> None:
    (opts, args) = parser.parse_args()

    repo = enclosing_repo()
    manager = Manager(repo)

    command = getattr(opts, "command", "generate")
    if command == "generate":
        prompt = opts.prompt
        if not prompt:
            if sys.stdin.isatty():
                prompt = open_editor(textwrap.dedent(EDITOR_PLACEHOLDER))
            else:
                prompt = sys.stdin.read()
        manager.generate_draft(prompt, OpenAIAssistant(), reset=opts.reset)
    elif command == "finalize":
        manager.finalize_draft(delete=opts.delete)
    elif command == "discard":
        manager.discard_draft(delete=opts.delete)
    else:
        assert False, "unreachable"


if __name__ == "__main__":
    main()
