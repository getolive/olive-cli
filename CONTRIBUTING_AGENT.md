# CONTRIBUTING_AGENT.md
## Purpose: This document contains detailed instructions including a prime checklist (i.e., tl;dr for agents) for how to work on this codebase.

## 0. Prime Checklist (agent TL;DR)
- [ ] All work begins with a spec and is tracked in real time.
- [ ] Code and specs must be self-documenting, self-healing, and easy to extend.
- [ ] Imports are deduped, grouped (system, third-party, project, local), and ordered by descending string length.
- [ ] Prefer dependency injection for context, preferences, and logger everywhere.
- [ ] ≥95% test coverage; assert only on public APIs and outputs.
- [ ] Never mutate or inspect registries, context, or files except through public APIs.
- [ ] All file operations go through the src tool or context API—never mutate files in place.
- [ ] All logging and user output uses provided logger and UI helpers; no debug prints in production.
- [ ] CI enforces formatting, lint, type checks, and full tests on every commit.
- [ ] Any exception to these rules must be justified in the relevant spec.

---

## 1. Builder Mode & Specs

- When initializing, Olive copies files from `~/.olive` into the project `.olive/` only if the file is not already present by name. Existing files are skipped (never overwritten) and reported in the CLI. This guarantees local customization is preserved.
- [ ] Begin all nontrivial work with a spec (FeatureSpec) including title, description, acceptance criteria, and ordered subtasks.
- [ ] Only act on the currently active spec.
- [ ] Update spec progress and comments in real time.
- [ ] Never perform silent or untracked work.

---

## 2. Imports & Module Structure
- [ ] Deduplicate all imports.
- [ ] Place all imports at the top of the file.
- [ ] Order imports by: (1) system/standard library, (2) third-party, (3) project (Olive), (4) local modules.
- [ ] Within each section, order imports by descending string length (most specific first).
- [ ] Remove all unused imports.
- [ ] For non-Python languages, follow that language’s idiomatic import convention; document any project-local exceptions.

---

## 3. Dependency Injection & State
- [ ] Use dependency injection for context, preferences, and logger in all utilities and CLI commands.
- [ ] Support explicit injection/mocking in all testable code.
- [ ] Use singletons (ToolRegistry, OliveContext) only when unavoidable and always allow injection.

---

## 4. Testing & Coverage
- [ ] Maintain ≥95% branch and error-path coverage for all code.
- [ ] Do not use @pytest.mark.asyncio on synchronous tests.
- [ ] Use pytest.skip or xfail for brittle/product-dependent tests, with reasons documented.
- [ ] After any code change, re-run pytest -x; tests must not crash pytest.
- [ ] Assert only on public APIs and outputs; never on private state or logs.
- [ ] In registry/command tests, use explicit setup and only public interfaces.

---

## 5. Registries & Tooling
- [ ] Register tools and commands only via public APIs or decorators.
- [ ] Never mutate or inspect registries except through get/list/dispatch methods.
- [ ] Ensure REPL/tool summaries accurately reflect discovered tools and use clear, styled output.
- [ ] Always use the canonical/singleton service registry; never create new ones unless specified by a spec.

---

- To extend system package support in the sandbox, use `sandbox.environment.base_apt_packages` (string or list) in `.olive/preferences.yml`. Olive will inject these at build-time, preserving Dockerfile best practices.
- [ ] Access context and preferences only via OliveContext and Preferences public APIs.
- [ ] Utilities must allow injected context/preferences for testing.
- [ ] Prevent global state leakage between tests; always reset or teardown.
- [ ] Perform all file operations through the src tool or public context API; never mutate files in place.

---

## 7. Logging & UI
- [ ] Use olive.logger.get_logger and olive.ui print_* helpers for all logging and output.
- [ ] Ensure all user-facing output is styled, concise, and free of debug prints in production.

---

## 8. Automation & Formatting
- [ ] Enforce black and isort (Python) or strictest formatter for the language.
- [ ] CI must lint, type-check, and run all tests on every commit.
- [ ] Update this checklist as soon as new code smells or needs are identified.

---

## 9. Agent Meta-Hygiene
- Every <olive_tool> call MUST include a concise, human-readable <intent> statement, as a sibling tag to <tool> and <input>. This intent must briefly explain why the tool is being invoked. Example:

  <olive_tool>
    <tool>spec</tool>
    <intent>Set this spec as active so all subsequent work is tracked correctly.</intent>
    <input>{"command": "set-active", "spec_id": "20250507_203644"}</input>
  </olive_tool>

  The <intent> is surfaced in UI/logs for transparency and auditability. If missing, it is a spec violation.
- [ ] Document any “grey area” or exceptions here and in the relevant spec.
- [ ] Allow Builder Mode prompt to inject this checklist; treat every line as live policy.
- [ ] Reference or store all maintenance/meta-specs here.

