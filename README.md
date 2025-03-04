# `git-draft(1)` [![CI](https://github.com/mtth/git-draft/actions/workflows/ci.yaml/badge.svg)](https://github.com/mtth/git-draft/actions/workflows/ci.yaml) [![Pypi badge](https://badge.fury.io/py/git-draft.svg)](https://pypi.python.org/pypi/git-draft/) [![codecov](https://codecov.io/gh/mtth/git-draft/graph/badge.svg?token=3OTKAI0FP6)](https://codecov.io/gh/mtth/git-draft)

> [!NOTE]
> WIP: Not quite functional yet.

## Highlights

* Concurrent editing. Continue editing while the assistant runs, without any
  risks of interference.


## Ideas

* Change prompt CLI inputs to `[PROMPT] [--] [ARGS]`. If `PROMPT` does not
  contain any spaces or `ARGS` (or `--`) is present, it will be interpreted as a
  template name. Otherwise an inline prompt.
* Only include files that the bot has written in draft commits.
* Add `--generate` timeout option.
* Add `Bot.state_folder` class method, returning a path to a folder specific to
  the bot implementation (derived from the class' name) for storing arbitrary
  data.
* Add URL and API key to `openai_bot`. Also add a compatibility version which
  does not use threads, so that it can be used with tools only. Gemini only
  supports the latter.
