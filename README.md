# 🫒 Olive — Local-First AI Dev Shell

**Olive** is a CLI-native, LLM-integrated operating system for developers. It
runs entirely on your machine, respects your privacy, and helps you build
faster by coordinating time, tasks, and tools — starting with itself.

> 🧠 Olive is not a co-pilot. It’s a structured, programmable, context-aware development tool for engineers who want to get more done.

---

## ✨ What Olive Does

- 🧠 Understands your codebase via ASTs, Git diffs, and tracked context
- 🛠 Implements features from specs it helps you write
- 🌀 Operates in Builder Mode to focus on your current goal
- 🧩 Uses tools you already know (shell, tmux, Docker) — no reinvention
- 🤖 Supports autonomy, security, and optional sandboxing
- 🧭 Respects your time, privacy, and local-first workflow

---

## 🧪 Quickstart

```bash
# Initialize Olive in your project
olive init

# Launch the interactive shell
olive shell

# Create a spec and activate Builder Mode
:spec create "Add OAuth login flow"
:spec use 20240428_104200
```

---

## 🧠 Collaborate with Olive

You can brainstorm ideas with Olive, then have it:

1. Write a structured spec (title, description, subtasks)
2. Track it in Builder Mode
3. Implement the code — with options for:
   - Interactive approvals
   - Fully autonomous patching
   - Secure sandboxed execution

This creates a continuous flow from idea → spec → implementation — all inside your terminal.

---

## 🔧 Tooling System

Olive tools are modular, typed, and safely invocable via shell or LLM.

```bash
:tools             # List available tools
:src get olive/shell.py
:spec complete 20240428_104200
```

Available tools include:

- `shell`: Run safe shell commands
- `src`: Modify source files with line-level precision
- `spec`: Manage structured work units
- `mcp`: (Coming soon) Issue multi-tool plans for higher-level control

Tools are composable from the shell, and extensible by developers.

---

## 🧱 Builder Mode

Specs are structured units of work — like GitHub issues, but executable.

```bash
:spec create "Implement LLM-aware planner"
:spec list
:spec use 20240428_104200
```

Each spec includes:

- ✅ Title & description
- 🔢 Subtasks (checklist)
- 💬 Comments
- 📁 Affected files
- 🔁 Git-backed progress

When a spec is active, Olive enters Builder Mode — reshaping its behavior and focus to help you complete that goal.

---

## 🪺 Sandbox Mode (Optional)

Olive can run in a fully isolated Docker sandbox:

- 🧠 Background daemon runs persistently in a tmux session
- 🛠 You can `docker exec`, `tmux attach`, or inspect volumes like any container
- 🔐 Gives you high-trust autonomy: Olive can patch, test, and commit safely
- 💡 Ideal for continuous flows and higher-order tool orchestration

Want Olive to just do the thing while you go make coffee? Enable sandboxing.

---

## 📂 Project Context

Olive builds a high-signal working context from:

- Source files you care about (automatically tracked)
- Git metadata and working diff
- Active spec, subtasks, and comments
- AST-level structure for smarter LLM prompting

Check it anytime:

```bash
olive context         # Show current context summary
olive context-files   # Dump hydrated file contents
```

---

## 🛠 Developer Internals

This repo includes:

- `olive/cli.py`: CLI entrypoint (Typer-based)
- `olive/shell.py`: REPL, commands, and interactive shell
- `olive/context/`: File hydration, AST extraction, metadata tracking
- `olive/tools/`: Tool registry, validation, dispatch (LLM + CLI)
- `olive/tasks/`: Async job engine, scheduler, result tracking
- `olive/daemon.py`: Local daemon lifecycle abstraction
- `olive/sandbox/`: Docker sandbox build/run, tmux management
- `olive/canonicals/`: Structured specs (Builder Mode)
- `olive/gitignore.py`: Git-aware context exclusion
- `olive/env.py`: Project root and path resolution
- `olive/preferences/`: User config and behavior toggles
- `olive/init.py`: Startup orchestration and validation

Every module is composable and testable. Olive is built to be built with.

---

## 🧭 Philosophy

Olive is not a co-pilot for vibe coding, it's a lever for engineers: Olive scales you.

The scaling laws were designed into Olive, it will automatically improve its usefulness with time and use.

Olive can be used to understand itself, extend itself, replicate itself, build
new applications, and integrate itself as a runtime component of your solution
architecture.

> Olives don't demand good weather to grow and civilizations were built around them.

---

## 📌 Status

Olive is **experimental** and under active development. Expect rapid iteration, sharp edges, and surprising usefulness.

Want to help build it? Activate a spec and start shipping.
