from __future__ import annotations

import optparse

parser = optparse.OptionParser(prog="draft")

parser.disable_interspersed_args()

command_group = optparse.OptionGroup(
    parser, "Commands", "exactly one command must be specified"
)
parser.add_option_group(command_group)


class Command:
    @classmethod
    def register(cls, name: str, **kwargs) -> Command:
        command = cls(name)
        command_group.add_option(
            command.flag,
            action="callback",
            callback=command,
            callback_args=(name,),
            **kwargs,
        )
        return command

    def __init__(self, name) -> None:
        self.name = name
        self._option_group = None

    @property
    def flag(self):
        return f"-{self.name[0].upper()}"

    def option_group(self) -> optparse.OptionGroup:
        if not self._option_group:
            self._option_group = optparse.OptionGroup(
                parser, f"Optional {self.flag} flags"
            )
            parser.add_option_group(self._option_group)
        return self._option_group

    def __call__(self, _option, _opt, value, parser, name) -> None:
        parser.values.command = name
        parser.values.command_args = value


Command.register(
    "create", help="create a draft", type="string", metavar="NAME"
)

Command.register(
    "prompt", help="read a prompt from stdin to add to the current draft"
)

apply_command = Command.register(
    "apply", help="apply the current draft to the original state"
)
apply_command.option_group().add_option(
    "-k",
    "--keep",
    help="do not delete the draft after applying",
    action="store_true",
)

Command.register("delete", help="delete the current draft")


(opts, args) = parser.parse_args()
command = getattr(opts, "command", None)
if command == "create":
    print("Creating draft...")
elif command == "prompt":
    print("Updating draft...")
elif command == "apply":
    print("Applying draft...")
elif command == "delete":
    print("Deleting draft...")
else:
    parser.error("missing command")
