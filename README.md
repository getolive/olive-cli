# Olive CLI — an agentic utility; repl, daemon, and runtime.

![Status](https://img.shields.io/badge/status-pre--v1,_experimental-orange)

**Olive CLI** is designed for engineers who prefer to work with AI as a tool/utility - with fine-grained control, customizability, and interop with existing standard tooling (like your shell, tmux, docker/podman, ollama, logging). It runs entirely on your machine (or optionally via OpenAI API-compatible cloud providers), optionally treating tasks as structured **Spec** objects (with clear objectives, checklists, context, and progress) instead of an open-ended chat. By using local models when available and real developer tools (files, shell, Git, Docker), Olive emphasizes transparency, reproducibility, and privacy over cloud-dependent or editor-locked solutions.

Olive is **not** a general-purpose “AI pair programmer” that just completes code in an IDE. It’s a lightweight, programmable development shell that can plan, generate, and integrate code with your guidance. All AI actions (like creating files, running tests, modifying code) are explicit, logged, and under your control – making Olive a high-end utility for power users who demand insight and auditability in AI-assisted coding.

## Key Features

- **Local-First Operation:** Optimized to run with local LLMs via [Ollama](https://ollama.com) for 100% offline use if desired. (Olive can also call OpenAI/Anthropic APIs if configured, but it prefers a local endpoint by default.) This contrasts with many other agentic coding tools (e.g. Anthropic’s *Claude Code* or VS Code-based *Cline*) which require cloud APIs – Olive lets you keep code and AI reasoning on your machine.

- **Structured Task Management:** Each coding task is a **Spec** (YAML/JSON file) with a title, description, checklist of subtasks, and contextual metadata. Specs are saved in your project (by default under a `.olive/` directory) and can be tracked in version control just like code. This provides an audit trail of what was asked and what steps were taken, which improves reproducibility and team knowledge sharing (you can review or share Specs via Git). Most alternative tools treat the session history implicitly or transiently – Olive makes tasks first-class artifacts.

- **Smart(ish) Context:** Olive automatically gathers context from your codebase to help the AI make relevant suggestions. It parses Abstract Syntax Trees and inspects Git diffs and file system structure to include only pertinent code snippets in prompts. This targeted context approach allows Olive to work on large projects without hallucinating about unrelated parts. You can also configure include/exclude rules in a YAML config (`~/.olive/` and project `.olive/`) to fine-tune what context is provided.

- **Extensible Tool System:** Olive exposes a small set of **tools** – safe, typed Python functions that the LLM can invoke to act on your environment. Out of the box, it includes:
  - **`src`** – read source code files (e.g. `src get <path>` to fetch file contents for review).
  - **`shell`** – run shell commands on your behalf (with safeguards).
  - **`spec`** – update or query the current Spec (e.g. mark checklist items complete).
  - **`mcp`** – a placeholder for “plan” actions (Model Context Protocol integration) – *experimental / on the roadmap*.

  Adding new tools is straightforward: you can write a Python function and register it, or even ask Olive to draft a new tool for you by following the pattern of existing ones (Olive can modify its own toolset if you permit it). This extensibility means Olive can evolve with your needs.

- **Multiple Execution Modes:** Olive supports different modes to balance focus and safety:
  - **Builder Mode** – the default interactive mode that keeps the AI focused on the *active Spec*. This narrows the AI’s attention to your current task.
  - **Sandbox Mode** – an isolated Docker container (with a tmux session) for executing commands or code that you don’t want running on your host machine. This is ideal for letting the AI run a build, test, or server in a controlled environment. You can toggle sandboxing on/off at runtime (`:sandbox on` command) to contain risky operations.
  - **Daemon Mode** – a persistent background process that keeps the model loaded and context warm. The daemon auto-starts when you launch `olive shell`, and it enables snappy responses by avoiding re-loading the model or context between commands. You can manage the daemon via `olive daemon ps/kill/attach`. Under the hood, Olive uses a file-based RPC in `.olive/run/` to communicate with the daemon, ensuring that whether you run tasks in the sandbox or host, the execution logic stays consistent.

- **Real Developer Tools Integration:** Olive doesn’t reinvent the wheel for editing or running code – it uses your filesystem and terminal. File edits are done via diffs or line ranges (and Olive always shows you the diff before applying it). Terminal commands are executed through the `shell` tool (under your confirmation or in the sandbox). It leverages **tmux** to keep long-running processes alive in the background (the daemon and sandbox each run in a tmux session). This design means you can inspect and intervene in any process.

- **Safety and Control:** All tool actions have validations and require the AI to specify *exactly* what to do. For example, file edits are constrained to specified line ranges or patterns to prevent uncontrolled changes, and commands can be run in dry-run mode if needed. Because tasks are broken into checklist items, you can step through complex changes one subtask at a time. Olive does **not** auto-apply irreversible actions without your go-ahead – it’s an assistant, not an autonomous agent running wild.

- **Configurability:** Olive’s behavior can be tuned via simple YAML configs. In `~/.olive/config.yml` you can set global preferences (like which OpenAI endpoint or local model to use, default model parameters, etc.), and per-project `.olive/config.yml` can override context inclusion rules or tool settings for that repository. Because these configs are code and text based, they can be reviewed or versioned.

## Installation

**Prerequisites:** Python 3.11+, and for certain features:
- **Docker** (if you plan to use Sandbox Mode for isolation).
- **tmux** (if you plan to use the background daemon or persistent sessions).
- **`uv` tool** (optional, for faster isolated Python env and package installs).

Olive is an early-stage project, so installation is from source:

1. **Clone the repository** and create a virtual environment:

   ```bash
   git clone https://github.com/getolive/olive-cli.git && cd olive-cli
   python3 -m venv .venv && source .venv/bin/activate   # or use `uv venv` for a quicker setup
   ```

2. **Install Python dependencies:**

   ```bash
   pip install -e .   # use -e for editable install (development mode)
   ```
   *Note:* If you have [`uv`](https://github.com/astral-sh/uv) you can instead run `uv pip install -e .` for an isolated and faster install.

3. **Initialize an Olive project:**

   ```bash
   source .venv/bin/activate
   olive init # (or % git init && olive init)
   ```
   This creates a `.olive/` directory in the current folder with the necessary subfolders (such as `specs/`, `run/`, etc.) and a default config. Each project you use Olive on should be initialized once.

Now you’re ready to use Olive in that project directory.

## Quick Start

Launch the interactive shell with:

```bash
source <path-to-olive-cli>/.venv/bin/activate
olive shell
```

This drops you into an Olive REPL (read-eval-print loop) where you can converse with the AI agent and issue special commands. Try `:help` to see all available commands. You can directly ask Olive to perform a task, for example:

> **You:** “Olive, set up a basic Flask web server in this project.”
> **Olive:** *(analyzes project context, maybe creates a new Spec with the plan)* …

Olive will likely create a Spec for the task (if you didn’t already start one) and begin outlining what files or code it plans to create or modify. It will then step through the checklist items, asking for confirmation before executing each action (like creating a file, writing code, running the app, etc.). You remain in control at each step.

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
    `:payload-summary`
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
- `:src get <path>` – Show the contents of a source file (you can use this to quickly view code; Olive’s AI also uses the `src` tool itself when it needs to read a file).
- `:spec complete <index>` – Mark a checklist item as completed (useful if you finished a step manually or want to skip it).
- `:sandbox on` / `:sandbox off` – Switch the execution environment into the Docker sandbox or back to host mode on the fly.
- `:daemon kill` – Stop the background daemon if it's running (you can also do this outside the shell with `olive daemon kill`).

You can always type natural language requests to Olive in the shell. For example, “Explain the design of the authentication module” or “Add a unit test for the `UserService` class.” Olive will process the request using the context of your project and either just answer (for explain-style queries) or create a Spec and start implementing (for development tasks).

## Core Concepts

- **Spec:** A *Spec* is an executable work unit (task) encapsulating what you want to achieve. It has a name, an optional description, and a checklist of sub-tasks or acceptance criteria. Olive represents Specs as files (YAML in `specs/` for persistent specs, or JSON in `run/tasks/` for active ones). Think of a Spec like a lightweight issue or story that the AI can help implement. Specs can be created by you (e.g. via `olive new-spec`) or by Olive itself when you give it a high-level instruction. By tracking Specs in Git, you can review how a feature was implemented or even revert a spec execution.

- **Tools:** Tools are discrete operations that Olive’s AI can invoke to interact with the environment. Under the hood, tools are Python functions with defined input schemas. Olive’s prompting strategy is *protocol-agnostic* – it presents available tool names, their purpose, and examples to the AI, and the AI responds by naming the tool and providing input when it decides to act. (No proprietary API or specific chain-of-thought format is enforced – if the model understands the concept of the tool from examples, it can use it.) This design means Olive isn’t tied to a single AI provider or paradigm; adding a new tool doesn’t require re-training, just telling the AI the tool exists. Current tools cover file reads, writing to the current spec, executing shell commands, and planning. More can be added easily.

- **Builder Mode:** When you’re working on a specific Spec, Olive narrows the AI’s focus to that context (this is Builder Mode). The system prompt and retrieval of context are oriented around “here’s the goal we’re working on right now.” This helps reduce distractions and keeps outputs relevant to the task at hand. Builder Mode is the typical mode during an `olive shell` session – you either select an existing Spec or let Olive create one, and then iteratively work through it.

- **Sandbox Mode:** In Sandbox Mode, Olive executes all shell commands inside an isolated Docker container. The container is set up using the project’s `./olive/sandbox/` directory (which can contain a Dockerfile and any context needed). When sandboxed, even if the AI tries a dangerous command (like installing packages or running a server), it won’t affect your host OS – you can monitor and terminate the tmux session if needed. This mode is useful for testing code in an environment similar to production, or simply containing side effects. If Docker or tmux is not available, this mode won’t function (Olive will warn you or fall back to host execution).

- **Daemon:** The Olive daemon is a background service that loads the language model and persists context between commands. When you run `olive shell`, it will automatically start a daemon (if not already running for that project) and attach your shell to it. The daemon process allows Olive to handle multiple tasks in parallel and watch for file changes or new tasks (it can react to triggers). Communication with the daemon happens through files: when a task is dispatched, Olive writes a JSON spec to `.olive/run/tasks/<id>.json` and the daemon eventually writes the result to `<id>.result.json`. This file-based RPC ensures that even if the sandbox is being used (which might be a separate container process), the commands and results flow through a unified interface on disk. For advanced users, you can start/stop and attach to the daemon’s tmux session manually (for debugging or to see raw model output streams).

- **Project Structure:** Olive keeps project-related data in a dedicated directory. By default, after `olive init`, you’ll have a structure like:

  ```
  .olive/
   ├── specs/          # saved Spec files (YAML definitions of tasks)
   ├── run/            # runtime files (temporary task files, results, RPC pipes)
   │   ├── tasks/      # incoming task specs and outputs (JSON)
   │   └── sbx/        # sandbox session working dirs and pipes
   ├── sandbox/        # Dockerfile and context for Sandbox Mode
   └── logs/           # logs of Olive sessions and interactions
  ```

You can clean `run/` anytime (it’s ephemeral), and you can review `logs/` to audit what Olive did in past sessions. The **specs** directory (and any config in `.olive/`) can be checked into source control if you want to share tasks or maintain a history of AI assistance in the project.

## Comparison to Other AI Coding Assistants

Olive exists in a growing ecosystem of *“agentic”* development tools. Here’s how it **differentiates itself** from some notable projects:

- **Editor Independence:** Olive is purely CLI-based and editor-agnostic. You use your own editors and terminals. Tools like **Cline** (AI assistant for VS Code) and **Windsurf** (Codeium’s AI IDE) are tied to specific editor environments. Olive instead integrates with standard developer workflows (shell, Git, Docker) without locking you into a particular IDE.

- **Local-Only Capability:** Olive can run completely offline with local models (via Ollama) – no API keys required. In contrast, **OpenAI’s Codex CLI** and **Anthropic’s Claude Code** depend on cloud APIs (OpenAI GPT-4 models and Claude respectively) and send your code to those services. **Plandex** can be self-hosted with open-source models, but by default it combines multiple cloud models for “strong” performance. Olive’s local-first design is ideal for privacy or working on proprietary code without sharing data.

- **Structured Tasks vs. Free-Form Chat:** Many coding assistants operate as an enhanced chat or command interface (you give an instruction, it tries to do it in one go). Claude Code, for example, lets you issue natural language commands in the terminal and it handles them, and **Codex CLI** similarly takes requests and attempts to apply changes. Olive takes a more structured approach: it formalizes the request into a Spec with a checklist, which can span multiple steps. This ensures complex tasks are broken down and each step is verified. **Plandex** has a similar concept of multi-step “plans” (with plan/tell modes and autonomy levels) but Olive’s persistence of the Spec on disk means the plan is not just in memory – it’s reviewable and modifiable outside the session as well.

- **Extensibility and Customization:** Olive’s tool plugin system is straightforward Python, which an individual engineer can extend on the fly. Other agents often have fixed toolsets or require configuration of external services for extension. For instance, Cline uses the Model Context Protocol (MCP) to allow creating new tools via external “providers,” but this is a networked approach and still experimental. Olive isn’t tied to MCP (though it plans to support it); you can drop in a new Python module under `olive/tools/` and it becomes available to the AI. This makes Olive highly **hackable** for power users. Additionally, Olive exposes config files for adjusting its prompts or behavior, whereas closed-source tools don’t allow modifying their prompt strategy or tool definitions.

- **Auditability and Logs:** Because Olive logs each task’s spec and outcome, it’s easy to retrace *“what exactly did the AI do?”*. Claude Code and others output information to the terminal, but unless you manually copy logs, the history may be lost once the session ends. Olive’s design, with `.result.json` outputs and log files, provides a paper trail. This is valuable for teams in regulated environments – even though Olive itself isn’t multi-user, a developer can commit the spec and diff that Olive produced, giving the team visibility into AI contributions.

- **Team Collaboration:** Olive is presently geared towards individual usage on a local repo. It does not have built-in multi-user or cloud sync features. By comparison, **Plandex** has an online mode with organization accounts for sharing plans, and Claude Code emphasizes assisting with git workflows which naturally fit team collaboration (e.g. preparing commits or PRs via commands). In Olive, collaboration would be done by sharing the Spec files or Git commits manually. If your team workflow is heavily Git-centric, Olive’s ability to handle Git operations is currently limited to what the AI does via the `shell` tool (for example, it could run `git add/commit` if you ask it to, but there’s no dedicated “open a PR” command built-in). In short, Olive can be used by teams (especially since it produces artifacts that can be code-reviewed), but it doesn’t (yet) have specialized multi-user support or integrations for project management – it’s primarily a personal productivity tool for now.

- **Experimental Status:** It’s worth noting that Olive CLI is a newer project (open-sourced in 2025) and is still **experimental**. It might not (yet) be as fully featured or polished as more mature tools. For example, Claude Code has the backing of Anthropic’s research into large-context models and is under active development with user feedback, and Windsurf is a commercial product evolving from Codeium. Olive’s advantage is agility and openness – it’s MIT/Apache licensed and welcomes contributions. If a feature is missing (say, web browsing capability or GUI integration), an advanced user could implement it in Olive’s framework. The roadmap for Olive includes deeper **MCP integration** (to speak the same “language” as tools like Cline for cross-compatibility), and a possible **“runtime” autonomous mode** in the future (where Olive could attempt to complete a whole Spec with minimal interaction, akin to a specialized Auto-GPT for coding tasks) – however, these features are in-progress and not yet reliable. We intentionally label Olive as experimental to set the expectation that it’s under rapid development and may change.

## Conclusion

Olive CLI is a distinct offering in the AI coding assistant landscape: it’s **lightweight and local**, with a focus on clarity, safety, and extensibility. It is particularly suited for senior engineers or enthusiasts who want to leverage AI assistance *on their own terms* – with full visibility into each action and the ability to shape the assistant to fit their workflow. If you enjoy the Unix philosophy of tools and transparency, Olive aims to bring that ethos to AI pair programming.

Give it a try, and feel free to contribute! Standard GitHub pull requests are welcome – the codebase is Python 3.11 with type hints, and we use `pytest` for testing (please ensure tests pass). We’re excited to collaborate with the community to push Olive forward.

## License

Olive CLI is open source under the Apache 2.0 License. © 2025 getolive.ai. This means you’re free to use and modify it, but it comes with no warranty – appropriate for an experimental tool. Happy hacking with Olive!
