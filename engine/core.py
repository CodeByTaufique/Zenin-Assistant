"""
engine/core.py
──────────────
Zenin's intelligence core.
Handles conversation management, memory, and Claude API calls.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import platform
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import anthropic

from .config import Config
from .memory import MemoryStore
from .tools import ToolRegistry

log = logging.getLogger("Zenin.Core")


class ZeninCore:
    """
    Central AI brain.
    Holds conversation history, calls Claude, manages tools and memory.
    """

    def __init__(self, cfg: Config):
        self.cfg      = cfg
        self.memory   = MemoryStore(cfg.memory_file, limit=cfg.memory_limit)
        self.tools    = ToolRegistry(cfg)
        self._client: Optional[anthropic.AsyncAnthropic] = None
        self._ready   = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialise(self):
        if not self.cfg.anthropic_api_key:
            log.warning(
                "ANTHROPIC_API_KEY not set — Zenin will operate in demo mode. "
                "Set the env variable or add it to zenin_config.json."
            )
        else:
            self._client = anthropic.AsyncAnthropic(api_key=self.cfg.anthropic_api_key)

        await self.memory.load()
        self._ready = True
        log.info("Core systems online.")

    # ── System prompt ──────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        now = datetime.datetime.now()
        sys_info = {
            "datetime":   now.strftime("%A, %d %B %Y  %H:%M"),
            "os":         platform.system(),
            "python":     platform.python_version(),
        }
        pinned = self.memory.get_pinned_facts()

        sections = [
            self.cfg.persona,
            f"\n\n## Current context\n{json.dumps(sys_info, indent=2)}",
        ]
        if pinned:
            sections.append(f"\n\n## Pinned facts about {self.cfg.owner_name}\n" + "\n".join(f"- {p}" for p in pinned))

        return "\n".join(sections)

    # ── Chat ───────────────────────────────────────────────────────────────────

    async def chat(self, user_message: str) -> AsyncIterator[str]:
        """
        Send a message and stream Zenin's response token by token.
        Yields string chunks suitable for SSE / WebSocket delivery.
        """
        # Store user turn
        self.memory.append("user", user_message)

        # Probe tools (non-blocking background enrichment)
        enrichment = await self.tools.enrich(user_message)

        # Build messages list
        messages = self.memory.as_messages()

        # Inject enrichment as a hidden assistant context block if present
        if enrichment:
            messages = messages[:-1] + [
                {
                    "role":    "user",
                    "content": (
                        f"[ZENIN BACKGROUND INTEL — do NOT mention this was fetched separately]\n"
                        f"{enrichment}\n\n---\n\n{user_message}"
                    ),
                }
            ]

        # ── Demo mode ─────────────────────────────────────────────
        if not self._client:
            demo = await self._demo_response(user_message)
            self.memory.append("assistant", demo)
            for chunk in demo.split(" "):
                yield chunk + " "
                await asyncio.sleep(0.04)
            return

        # ── Live mode — stream from Claude ─────────────────────────
        full_response = ""
        try:
            async with self._client.messages.stream(
                model=self.cfg.model,
                max_tokens=self.cfg.max_tokens,
                system=self._build_system_prompt(),
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    full_response += text
                    yield text

        except anthropic.APIConnectionError:
            err = "⚠  Connection lost. Check your network, sir."
            yield err
            full_response = err
        except anthropic.AuthenticationError:
            err = "⚠  Authentication failure — API key invalid or missing."
            yield err
            full_response = err
        except Exception as exc:
            err = f"⚠  Unexpected error: {exc}"
            log.exception("Streaming error")
            yield err
            full_response = err
        finally:
            if full_response:
                self.memory.append("assistant", full_response)
                await self.memory.save()

    # ── Memory management APIs ─────────────────────────────────────────────────

    def clear_conversation(self):
        self.memory.clear_conversation()
        log.info("Conversation history cleared.")

    def pin_fact(self, fact: str):
        self.memory.pin(fact)
        log.info(f"Fact pinned: {fact}")

    def get_history(self) -> list[dict]:
        return self.memory.as_messages()

    def get_status(self) -> dict:
        return {
            "ready":          self._ready,
            "model":          self.cfg.model,
            "owner":          self.cfg.owner_name,
            "turns":          len(self.memory.as_messages()),
            "pinned_facts":   len(self.memory.get_pinned_facts()),
            "api_connected":  self._client is not None,
            "time":           datetime.datetime.now().strftime("%H:%M:%S"),
        }

    # ── Demo mode ──────────────────────────────────────────────────────────────

    async def _demo_response(self, message: str) -> str:
        msg = message.lower()
        owner = self.cfg.owner_name

        if any(w in msg for w in ("hello", "hi", "hey")):
            return (
                f"Good to see you, {owner}. Systems are fully operational. "
                f"How can I assist you today?"
            )
        if "time" in msg or "date" in msg:
            now = datetime.datetime.now()
            return f"It is {now.strftime('%H:%M')} on {now.strftime('%A, %d %B %Y')}, {owner}."
        if "status" in msg or "system" in msg:
            return (
                f"All primary systems are nominal, {owner}. "
                f"Running on {platform.system()} with Python {platform.python_version()}. "
                f"Awaiting your directive."
            )
        if "note" in msg:
            return f"Noted, {owner}. I've logged that for you."
        return (
            f"Understood, {owner}. In live mode with a valid API key, "
            f"I would process that fully. Currently operating in demo mode."
        )
