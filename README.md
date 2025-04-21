# 🫒 Olive CLI — Local‑First AI Development Shell [status: experimental]

Olive CLI is an agentic coding utility. Olive can be run as a repl (% olive
shell) and a daemon (% olive --daemon shell). Olive has an optional
containerized sandbox environment for command execution, or it can execute on your
host. 

Olive is customizable down to the shell prompt and llm system prompts. Host
configuration is managed by you in ~/.olive, and project configuration is
managed by olive in ./.olive (i.e., your project directory).

Olive ships with some tools and makes it very easy to add more. You can ask
olive to create tools for itself for you, following the pattern of tools it
has.

Olive transparently interoperates with git, tmux, and docker rather than
creating new standards for things these tools already excel at, for example for
managing builder mode & specifications (specs) via git, and daemon sessions via
tmux, and sandboxing via containers.

Olive is experimental.

### 🧠 Local Models, Real Tools

**[Ollama](https://ollama.com) + Olive — a match made in heaven.**
Olive prefers local execution via Ollama, using an OpenAI-compatible API.

Tool use? Protocol-agnostic by design. Olive just names the tools, describes
what they do, and shows a couple examples.

MCP is on the roadmap — it's becoming a lingua franca — but Olive isn’t locked
to any protocol or framework.

> A working thesis: as models get smarter, the best interface is clarity of
> purpose, crisp examples, and real practice. Just like with people.


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
uv venv && source .venv/bin/activate

# Install dependencies using uv (recommended)
uv pip install -e .

# Run Olive init to initialize project structure
olive init
```

# 4. bootstrap user config
### Quick Start

```bash
olive shell # and then type ```:help``` or just ask olive about itself and what you'd like to do.
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

---
## Contributing

Standard GitHub Pull Requests are welcome. Please ensure unit tests (`pytest`) pass and follow the existing code style (`ruff`, `mypy`).

---
## License

Apache License 2.0 © 2025 getolive.ai
