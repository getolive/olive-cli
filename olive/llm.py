# cli/olive/llm.py

"""
LLM interaction and orchestration module for Olive.

Handles prompt preparation, tool metadata injection, abstract mode summarization,
streamlined file context, and interaction with OpenAI-compatible LLM providers.
"""

from pathlib import Path
from typing import List

import tiktoken
import yaml
from openai import OpenAI
import openai
import asyncio
from olive.ui import console
from olive.session import _INTERRUPTED

from olive.context import context
from olive.logger import get_logger
from olive.preferences import prefs
from olive.tasks import task_manager
from olive.tools import tool_registry

logger = get_logger("llm")


class LLMProvider:
    def __init__(self):
        self.model = prefs.get("ai", "model", default="gpt-4")
        self.temperature = prefs.get("ai", "temperature", default=0.7)
        self.timeout = prefs.get("ai", "timeout", default=30)
        self.base_url = prefs.get("ai", "base_url", default="https://api.openai.com/v1")
        self.provider = prefs.get("ai", "provider", default="openai")
        self.api_key = self.load_credentials(self.provider)

        if not self.api_key:
            logger.warning(f"No API key found for provider '{self.provider}'.")
        else:
            logger.debug(f"Loaded API key for provider: {self.provider}")

        try:
            self.client = OpenAI(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
            )
            logger.info(
                f"LLM client initialized for provider '{self.provider}' using {self.model}"
            )
        except Exception as e:
            self.client = None
            logger.exception(
                f"Failed to initialize LLM client for provider '{self.provider}': {e}"
            )

    def load_credentials(self, provider_name=None):
        path = Path.home() / ".olive" / "credentials.yml"
        if not path.exists():
            logger.warning("No ~/.olive/credentials.yml found.")
            return None
        creds = yaml.safe_load(path.read_text())
        return creds.get(provider_name, {}).get("api_key", None)

    def build_payload(self, prompt: str, dry_run: bool = False):
        messages = self._build_context_messages(prompt)

        try:
            enc = tiktoken.encoding_for_model(self.model)
            token_count = sum(len(enc.encode(m["content"])) for m in messages)
        except Exception:
            token_count = len(str(messages))

        stats = {
            "provider": self.provider,
            "provider_base_url": self.base_url,
            "token_count": token_count,
            "files": [f.model_dump() for f in context.state.files],
            "model": self.model,
            "max_tokens": prefs.get("context", "max_tokens", default=80000),
        }

        return (messages, stats) if dry_run else messages

    def _build_context_messages(self, prompt: str) -> List[dict]:
        """
        Build the full LLM chat payload including:
        - System prompt
        - Recent user/assistant messages
        - Final user prompt, optionally augmented with metadata or file context

        Abstract mode determines whether we inject metadata summaries or raw file content.
        """
        from olive.context.utils import render_file_context_for_llm

        context.hydrate()
        messages = []

        # 1. System prompt
        system_content = "\n\n".join(
            s.strip() for s in context.state.system if s.strip()
        )
        messages.append({"role": "system", "content": system_content})

        # 2. Prior chat (user + assistant)
        messages.extend(
            m.model_dump()
            for m in context.state.chat
            if m.role in ("user", "assistant")
        )

        # 3. Inject user-facing context
        user_blocks = render_file_context_for_llm()

        # 4. Final user message
        injected = "\n\n".join(user_blocks).strip()
        full_user_prompt = f"{prompt}\n\n--\n\n{injected}" if injected else prompt
        messages.append({"role": "user", "content": full_user_prompt})

        # 5. Logging preview
        logger.info("=== LLM Payload ===")
        for i, m in enumerate(messages):
            snippet = m["content"][:200].replace("\n", " ")
            logger.info(f"[{i}] {m['role']}: {snippet}... ({len(m['content'])} chars)")
        logger.info("====================")

        return messages

    def mock_ask(self, prompt: str):
        return self.build_payload(prompt, dry_run=True)

    async def ask(
        self,
        prompt: str,
        _depth: int = 0,
        _max_depth: int = 128,  # recursion guard
        _retries: int = 2,  # shared retry budget for recoverable errors
        _retry_delay: float = 2.0,  # initial back‑off seconds
    ):
        """
        Ask the LLM, dispatch tools, recurse with tool outputs.
        Retries only on recoverable errors (rate‑limit, 5xx, connection).
        Thread‑safe spinner via olive.ui.console_lock().
        """

        # ── Guard clauses ────────────────────────────────────────────────
        if not prompt.strip():
            logger.warning("llm.ask called with empty prompt. Skipping.")
            return

        if not self.api_key or not self.client:
            logger.warning("No API key or client available.")
            return "[Mocked response: no API key found]"

        if _depth >= _max_depth:
            logger.warning("Max LLM recursion depth reached; aborting.")
            return "[Aborted: too many tool cycles. You can continue by just asking olive to please continue. This is a failsafe.]"

        # ── Helper: classify recoverable errors ──────────────────────────
        def _is_recoverable(err: Exception) -> bool:
            if isinstance(
                err,
                (
                    openai.RateLimitError,
                    openai.APIConnectionError,
                ),
            ):
                # "insufficient_quota" → unrecoverable even if RateLimitError
                return "insufficient_quota" not in str(err).lower()
            if isinstance(err, openai.APIError):
                status = getattr(err, "status_code", 0)
                return 500 <= status < 600  # retry only on 5xx
            return False  # 4xx auth / invalid‑request → unrecoverable

        # ── 1. Call the model with limited retries ──────────────────────
        try:
            messages = self.build_payload(prompt)
            with console.status("[bold cyan]Thinking…[/bold cyan]", spinner="dots"):
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
        except Exception as e:
            if _is_recoverable(e) and _retries > 0:
                logger.warning(
                    f"LLM call failed ({e.__class__.__name__}: {e}). "
                    f"Retrying in {_retry_delay:.1f}s…"
                )
                await asyncio.sleep(_retry_delay)
                return await self.ask(
                    prompt,
                    _depth=_depth,
                    _max_depth=_max_depth,
                    _retries=_retries - 1,
                    _retry_delay=_retry_delay * 2,
                )
            logger.exception(f"Unrecoverable LLM error: {e}")
            return f"[LLM error: {e}]"

        # ── 2. Normal success path ──────────────────────────────────────
        reply = response.choices[0].message.content.strip()
        logger.info("Prompt and context sent to LLM.")

        context.append_chat("user", prompt)
        context.append_chat("assistant", reply)
        context.save()

        task_ids = tool_registry.process_llm_response_with_tools(reply, dispatch=True)
        if not task_ids:
            return reply  # final answer — no tools requested

        # ── 3. Await tool tasks concurrently ────────────────────────────
        results = await asyncio.gather(
            *(task_manager.wait_for_result(tid) for tid in task_ids),
            return_exceptions=True,
        )
        outputs = [
            r.output
            for r in results
            if hasattr(r, "output") and r.output not in (None, "")
        ]
        logger.debug(
            f"Completed {len(task_ids)} tool task(s); "
            f"{len(outputs)} produced non‑empty output."
        )

        if not outputs:
            return reply  # tools produced nothing useful

        # ── 4. Recurse once with tool outputs ───────────────────────────
        # ── 4. Recurse once with tool outputs ───────────────────────────
        if _INTERRUPTED.is_set():
            print("[Olive] Recursion paused by user (Ctrl+C). Type ':resume' to continue.")
            return "[Paused: Ctrl+C interrupt]"
        followup = "\n\n".join(map(str, outputs))
        return await self.ask(
            followup,
            _depth + 1,
            _max_depth,
            _retries,  # propagate remaining retries
            _retry_delay,
        )
