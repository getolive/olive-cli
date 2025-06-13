# Olive CLI
### olive-cli is an llm-based operating system for engineers packaged as a terminal app.

![Status](https://img.shields.io/badge/status-pre--v1,_experimental-orange)

```bash
# setup venv (3.12 stable)
uv venv --python=3.12

# install (minimal)
uv pip install "git+https://github.com/getolive/olive-cli.git"

# install (recommended, PEP508 with all optionals except voice included)
uv pip install "olive[dev,http,syntax] @ git+https://github.com/getolive/olive-cli.git"

# install (PEP508 with all optionals including voice included)
uv pip install "olive[dev,http,syntax,voice] @ git+https://github.com/getolive/olive-cli.git"

# get started
olive --help
```

# initialization

Olive will initialize with defaults, first from the olive's dotfile_defaults/, then from ~/.olive, and finally from .olive. This means you can customize olive down to the individual project and sandbox.


```bash
git init    # olive requires git, using git to manage branching for specs and other things.
olive init  # creates ~/.olive if required, .olive if required, validates install is healthy.
olive shell # the repl
```

## dependencies:
```
POSIX host
docker (if using sandbox support)
astral's uv
python 3.12 (venv)
```

**Olive CLI** is designed for engineers who prefer teminal applications and are looking for an open, extensible, transparent, and optionally 100% local engineering utility that helps them get more done.

https://github.com/user-attachments/assets/20f1964a-8e0d-42d0-a733-d42f6f840c57

## Key Features

- Full customizability (see olive/dotfile_examples/preferences.yml)
- Containerized sandbox execution environment (docker) per running olive-cli instance
- Built-in base tools (build/add your own; pure python & text)
- Built-in canonical for a work specification & tool ("spec") [define objectives, break down into (sub)tasks]: better quality outputs.
- Optional extras: voice (voice mode - STT), syntax (abstract syntax tree for code (highly reccomended)), dev (for working on olive-cli)
- Transparent file-based RPC to review, optionally re-play, and audit all llm/sandbox/tool interactions
- LLM engine can be local or cloud (i.e., OpenAI compatible api endpoint required)
- Voice mode includes built-in dual whisper models for 100% local transcription

## Quick Start

Launch the interactive shell with ```olive shell```:

```bash
cd <project-root>
uv venv --python=python3.12
source <project-root>/.venv/bin/activate
olive shell
```

This drops you into the REPL which is the preferred way to interact live with olive-cli. Try `:help` in the repl to see all available commands.
There are other ways to interact with olive-cli including as daemon and ad-hoc via commands with instruction payloads. 

> **You:** “Please demo yourself: create a fizzbuzz program in python, create a fizzbuzz program in C. compile the C program as a library/module. update the python fizzbuzz program to call both the python fizzbuzz and the C fizzbuzz from the module and print out the results of both calls."

> **Olive:** *(analyzes project context, maybe creates a new Spec with the plan, or one-shots it if minimal ambiguity)* …

Within the shell, lines starting with `:` are **meta-commands** for the Olive interface (not sent to the AI). Some useful ones:

## Shell Command Input Modes

Once inside the Olive shell (`olive shell`), you can interact in several ways:

- **Natural Language (no prefix):**
  - Just type your request or instruction.
    _Example:_
    `Add a configuration loader for YAML files.`
- **Meta-commands (`:`):**
  - Commands for controlling Olive itself (not sent to the AI).
    _Examples:_
    `:help`
    `:messages`
    `:tools`
    `:spec complete 1`
- **Shell commands (`!`):**
  - Run a shell command directly on your host or in sandbox mode.
    _Example:_
    `!ls -la` or `!nvim .`
- **Active Shell commands (`!!`):**
  - Shortcut for a tool call - i.e., runs your command inside the LLM's execution environment.
    _Example:_
    `!!shell ls -la`
- **One-off scripting (`olive shell -c "..."`):**
  - Run a single command or query without launching the interactive shell.
    _Example:_
    `olive shell -c "Summarize the purpose of src/context.py"`

All input is processed in context: meta-commands and shell commands are executed immediately, while natural language is given to the AI with your current project’s context and spec.

- `:exit` – Exit olive's REPL.
- `:tools` – List all tools available to the AI (and whether they’re currently allowed).
- `:spec list` – Review currently available specifications for this project
- `:sandbox-start [--force]` / `:sandbox-stop` – Sandbox start/stop if sandbox is enabled in your project-root/.olive/settings/preferences.yml

You can always type natural language requests to Olive in the shell. For example, “Explain the design of the authentication module” or “Add a unit test for the `UserService` class.” Olive will process the request using the context of your project and either just answer (for explain-style queries) or create a Spec and start implementing (for development tasks).

## Project-specific Sandbox System Packages

### extra apt packages on the sandbox

Set `sandbox.environment.extra_apt_packages` in your `.olive/settings/preferences.yml` (string or list) to inject additional apt packages into the sandbox Dockerfile’s base layer.

Example:
```yaml
sandbox:
  environment:
    extra_apt_packages:
    - cowsay bc  # start olive shell, then at the repl type !!shell /usr/games/cowsay moo, or !!shell bc
```

This enables per-project system dependency management for Olive sandboxes.

### extra project-specific pages (e.g., pip for a python project, etc)

Project sandbox packages should be managed from the Dockerfile for the project, located at 
```project-root/.olive/sandbox/Dockerfile```

Locate the section "Use this section for project-specific includes" and make your changes
Example:
```
RUN /opt/venv/bin/pip install markdownify
```

## Olive's settings paths

Olive manages user-level configuration in ~/.olive, and manages per-project level config at project-root/.olive for each project-root in which you use olive.

Example project-root/.olive (subset):

  ```
  .olive/
   ├── specs/          # saved Spec files (YAML definitions of tasks)
   ├── run/            # runtime files (temporary task files, results, RPC pipes)
   │   ├── tasks/      # incoming task specs and outputs (JSON)
   │   └── sbx/        # sandbox session working dirs and pipes
   ├── sandbox/        # Dockerfile and context for Sandbox Mode
   └── logs/           # logs of Olive sessions and interactions
  ```

You can clean that `run/` anytime (it’s ephemeral), and you can review `logs/` to audit what Olive did in past sessions. The **specs** directory (and any config in `.olive/`) can be checked into source control if you want to share tasks or maintain a history of AI assistance in the project.

The best way to learn more about olive and go deep is to clone the repo, create your venv, install olive as editable within your olive-cli/ project root venv and open ```olive shell``` and ask olive to explain and work through examples with you live.

## License

Olive CLI is open source under the Apache 2.0 License. This means you’re free to use and modify it, but it comes with no warranty – appropriate for an experimental tool. Happy hacking with Olive!
