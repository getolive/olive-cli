# cli/olive/llm.py

"""
High‑performance LLM orchestration for Olive.
------------------------------------------------
• End‑to‑end async with openai.AsyncClient (falls back to thread‑pool).
• Integrated spinner + immediate Ctrl‑C cancellation via @cancellable.
• Structured retries & recursion identical to legacy behaviour.
"""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path
from typing import List

import openai
import tiktoken
import yaml
from openai import AsyncClient, OpenAI

from olive.context import context
from olive.logger import get_logger
from olive.preferences import prefs
from olive.shell.utils import cancellable
from olive.tasks import task_manager
from olive.tools import tool_registry

logger = get_logger("llm")


class LLMProvider:
    """Singleton‑style wrapper around OpenAI‑compatible chat models."""

    def __init__(self):
        # ── Preferences --------------------------------------------------
        self.model = prefs.get("ai", "model", default="gpt-4o-mini")
        self.temperature = prefs.get("ai", "temperature", default=0.7)
        self.timeout = prefs.get("ai", "timeout", default=30)
        self.base_url = prefs.get("ai", "base_url", default="https://api.openai.com/v1")
        self.provider = prefs.get("ai", "provider", default="openai")

        # ── Credentials --------------------------------------------------
        self.api_key = self._load_credentials(self.provider)
        if not self.api_key:
            logger.warning("No API key found for provider '%s'.", self.provider)

        # ── Client(s) ----------------------------------------------------
        self.client: OpenAI | None = None  # blocking variant
        self.aclient: AsyncClient | None = None  # preferred async
        try:
            self.client = OpenAI(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
            )
            self.aclient = AsyncClient(
                api_key=self.api_key, base_url=self.base_url, timeout=self.timeout
            )
            logger.info(
                "LLM client initialised for '%s' → %s", self.provider, self.model
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to initialise LLM client: %s", exc)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _load_credentials(self, provider_name: str | None = None):
        cred_path = Path.home() / ".olive" / "credentials.yml"
        if not cred_path.exists():
            return None
        creds = yaml.safe_load(cred_path.read_text()) or {}
        return creds.get(provider_name, {}).get("api_key")

    # ------------------------------------------------------------------
    # Payload construction (unchanged)
    # ------------------------------------------------------------------
    def build_payload(self, prompt: str, dry_run: bool = False):
        """Return full chat payload *or* (messages, stats) when dry‑run."""
        messages = self._build_context_messages(prompt)

        # token accounting (best‑effort)
        try:
            enc = tiktoken.encoding_for_model(self.model)
            token_count = sum(len(enc.encode(m["content"])) for m in messages)
        except Exception:  # noqa: BLE001
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
        # Identical logic as in legacy version (system → chat history → file ctx → prompt)
        from olive.context.utils import render_file_context_for_llm

        context.hydrate()
        msgs: List[dict] = []

        # 1 · system prompt
        system_content = "\n\n".join(
            s.strip() for s in context.state.system if s.strip()
        )
        msgs.append({"role": "system", "content": system_content})

        # 2 · prior chat
        msgs.extend(
            m.model_dump()
            for m in context.state.chat
            if m.role in ("user", "assistant")
        )

        # 3 · file context
        injected_blocks = render_file_context_for_llm()
        injected = "\n\n".join(injected_blocks).strip()

        # 4 · final user prompt
        full_user_prompt = f"{prompt}\n\n--\n\n{injected}" if injected else prompt
        msgs.append({"role": "user", "content": full_user_prompt})

        # preview to log
        logger.info("=== LLM Payload ===")
        for i, m in enumerate(msgs):
            logger.info(
                "[%d] %s: %s… (%d chars)",
                i,
                m["role"],
                m["content"][:200].replace("\n", " "),
                len(m["content"]),
            )
        logger.info("====================")
        return msgs

    def mock_ask(self, prompt: str):
        return self.build_payload(prompt, dry_run=True)

    # ------------------------------------------------------------------
    # Public API – ask()
    # ------------------------------------------------------------------
    @cancellable(message="[bold cyan]Thinking…[/bold cyan]", spinner="dots")
    async def ask(
        self,
        prompt: str,
        _depth: int = 0,
        _max_depth: int = 16,
        _retries: int = 2,
        _retry_delay: float = 2.0,
    ):
        """See previous docstring – behaviour preserved; cancellation by decorator."""

        if not prompt.strip():
            logger.warning("llm.ask called with empty prompt. Skipping.")
            return
        if not self.api_key or not self.client:
            logger.warning("No API key or client available.")
            return "[Mocked response: no API key found]"
        if _depth >= _max_depth:
            logger.warning("Max LLM recursion depth reached; aborting.")
            return "[Aborted: too many tool cycles. Ask Olive to continue.]"

        def _is_recoverable(err: Exception) -> bool:
            if isinstance(err, (openai.RateLimitError, openai.APIConnectionError)):
                return "insufficient_quota" not in str(err).lower()
            if isinstance(err, openai.APIError):
                return 500 <= getattr(err, "status_code", 0) < 600
            return False

        # ------------------------------------------------------------------
        # 1 · model call (async preferred, else thread‑pool)
        # ------------------------------------------------------------------
        try:
            messages = self.build_payload(prompt)
            if self.aclient:
                response = await self.aclient.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                )
            else:
                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    partial(
                        self.client.chat.completions.create,
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                    ),
                )

        except asyncio.CancelledError:
            logger.info("LLM call cancelled by user.")
            raise
        except Exception as exc:  # noqa: BLE001
            if _is_recoverable(exc) and _retries > 0:
                logger.warning(
                    "LLM error (%s): %s – retrying in %.1fs",
                    type(exc).__name__,
                    exc,
                    _retry_delay,
                )
                await asyncio.sleep(_retry_delay)
                return await self.ask(
                    prompt,
                    _depth=_depth,
                    _max_depth=_max_depth,
                    _retries=_retries - 1,
                    _retry_delay=_retry_delay * 2,
                )
            logger.exception("Unrecoverable LLM error: %s", exc)
            return f"[LLM error: {exc}]"

        # ------------------------------------------------------------------
        # 2 · normal success path
        # ------------------------------------------------------------------
        reply = response.choices[0].message.content.strip()
        context.append_chat("user", prompt)
        context.append_chat("assistant", reply)
        context.save()

        task_ids = tool_registry.process_llm_response_with_tools(reply, dispatch=True)
        if not task_ids:
            return reply

        results = await asyncio.gather(
            *(task_manager.wait_for_result(tid) for tid in task_ids),
            return_exceptions=True,
        )
        outputs = [
            r.output
            for r in results
            if hasattr(r, "output") and r.output not in (None, "")
        ]
        if not outputs:
            return reply

        followup = "\n\n".join(map(str, outputs))
        return await self.ask(followup, _depth + 1, _max_depth, _retries, _retry_delay)
