# `git-draft(1)` [![CI](https://github.com/mtth/git-draft/actions/workflows/ci.yaml/badge.svg)](https://github.com/mtth/git-draft/actions/workflows/ci.yaml) [![codecov](https://codecov.io/gh/mtth/git-draft/graph/badge.svg?token=3OTKAI0FP6)](https://codecov.io/gh/mtth/git-draft) [![Pypi badge](https://badge.fury.io/py/git-draft.svg)](https://pypi.python.org/pypi/git-draft/)

> [!NOTE]
> WIP: Unstable API.


## Highlights

* Concurrent edits. By default `git-draft` does not touch the working directory.
* Customizable prompt templates.
* Extensible bot API.


## Installation

```sh
pipx install git-draft[openai]
```


## Next steps

* Mechanism for reporting feedback from a bot, and possibly allowing user to
  interactively respond.
* Add configuration option to auto sync and `--no-sync` flag. Similar to reset.
  Also rename both options to `sync` and `reset`, this will make it more natural
  to support a similar config option for `accept`.
* Add `--sync` `finalize` option which creates a additional commit when
  finalizing if any changes were added to the bot's output. This could be useful
  training data, showing what the bot did not get right.
* Convenience `--accept` functionality for simple cases: checkout option which
  applies the changes, and finalizes the draft if specified multiple times. For
  example `git draft -aa add-test symbol=foo`
* Support file rename tool.
  * https://stackoverflow.com/q/49853177/1062617
  * https://stackoverflow.com/q/6658313/1062617
