# 🫒 Olive CLI — Local‑First AI Development Shell

Olive CLI is an experimental command‑line workspace that lets you plan, generate and integrate code on your own machine. It treats tasks as structured *Specs*, exposes a small, typed tool set to an LLM in an agnostic way, and optionally isolates work using Docker for sandboxing (otherwise can use its host).

---
## Feature Summary

| Area | Included |
|------|--------------------|
| **Task management** | *Spec* objects (title, checklist, context, progress) |
| **Context engine** | AST parsing, Git diff inspection, file‑system filters |
| **Tool registry** | `src`, `shell`, `spec`, `mcp` (plan), extensible via Python |
| **Execution modes** | • **Builder Mode** (focus on active Spec) <br>• **Sandbox Mode** (Docker container + tmux) <br>• Host‑side daemon with tmux |
| **Safety** | File‑range editing, dry‑runs, typed tool validation |
| **Configuration** | YAML preferences in `~/.olive`, git‑aware context inclusion/exclusion |


---
## Installation

### Prerequisites

* **Python ≥ 3.9** (CPython)
* **Docker Desktop or engine** (required for Sandbox Mode)
* **tmux** (required only if you intend to run the host‑side daemon)
* **uv** <https://github.com/astral-sh/uv> (recommended for fast, isolated package installs)

### Steps

```bash
# 1. clone the repo
$ git clone https://github.com/USERNAME/olive-cli.git
$ cd olive-cli

# 2. create an isolated Python environment (pick one)
$ uv venv .venv            # fast, PEP 582‑style
$ source .venv/bin/activate

# 3. install Olive in editable mode
$ uv pip install -e .      # or: (or uv pip install -e ".[dev]")

# 4. bootstrap user config
$ mkdir -p ~/.olive
$ cp -r dotfile_examples/* ~/.olive/    # and edit them to your liking.

# 5. start using Olive inside any project directory
$ cd /path/to/your/project && source <path to olive's venv from step 2>
$ olive init               # generates local .olive/ project
$ olive shell              # enter interactive REPL
```

---
## Quick Start

```bash
:spec create "Add OAuth login"
:spec use                   # activates latest Spec
# Olive enters Builder Mode and proposes a plan
```

Key commands:

| Command | Purpose |
|---------|---------|
| `:tools` | list available tools |
| `:src get <file>` | inspect file contents |
| `:spec complete` | mark checklist items done |
| `:sandbox on` | move execution into Docker |

---
## Core Concepts

* **Spec** – Executable work unit, tracked in Git.
* **Builder Mode** – Narrowed prompt & context for the active Spec.
* **Tool** – Safe function the LLM can call; implemented in Python.
* **Sandbox Mode** – Docker container + tmux session for autonomous work.

---
## Project Layout (selected modules)

```
olive/
 ├─ cli.py            # Typer entrypoint
 ├─ shell.py          # REPL commands & dispatch
 ├─ context/          # file hydration, AST, preferences
 ├─ tools/            # src, shell, spec, …
 ├─ sandbox/          # Docker build/run helpers
 └─ tasks/            # async job engine
```

---
## Contributing

Standard GitHub Pull Requests are welcome. Please ensure unit tests (`pytest`) pass and follow the existing code style (`ruff`, `mypy`).

---
## License

Apache License 2.0 © 2025 getolive.ai
