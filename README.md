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

* **Python ≥ 3.11** (CPython)
* **Docker Desktop or engine** (required for Sandbox Mode)
* **tmux** (required only if you intend to run the host‑side daemon)
* **uv** <https://github.com/astral-sh/uv> (recommended for fast, isolated package installs)
### Steps

### Install

```bash
# Clone the repo
git clone https://github.com/getolive/olive && cd olive

# Create a fresh virtual environment
python3.11 -m venv .venv && source .venv/bin/activate

# Install dependencies using uv (recommended)
uv pip install -e .

# Run Olive once to initialize project structure
olive
```

# 4. bootstrap user config
### Quick Start

```bash
olive spec create "Add GitHub OAuth"
olive spec use
```

This activates **Builder Mode**, where Olive focuses on a specific feature (`spec`) and proposes a concrete plan.

From there, use `olive shell` to enter a conversational CLI that supports planning, editing, and tool execution.

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





































































































































































































































































































































































































































































































































































































































































































































































































































































































































## Tasks & File-RPC

Olive executes all work as structured **tasks**. These are written to disk and dispatched to the daemon
using a file-based RPC system. This ensures parity between host and sandboxed environments.

Each task uses a `.json` spec file and produces a `.result.json` output.

```bash
olive run-task --file my_task.json
```

Locations:

- Input: `.olive/run/tasks/<id>.json`
- Output: `.olive/run/tasks/<id>.result.json`
- Daemon RPC: `.olive/run/sbx/<session_id>/rpc`

## Daemon Behavior

Every Olive project can run a background **daemon** process. This keeps context warm, enables fast shell
execution, and avoids reloading models or context between runs.

The daemon is automatically started when needed (e.g. `olive shell`) and can be managed manually:

```bash
olive daemon ps         # list running daemons
olive daemon kill       # stop background process
olive daemon attach     # resume tmux session
```

## Project Layout

```text
.olive/
├── run/              # ephemeral runtime paths
│   ├── tasks/        # task specs + results
│   └── sbx/          # sandbox session roots
├── sandbox/          # Dockerfile, build context
├── specs/            # feature specs (YAML)
└── logs/             # persistent logs
```
