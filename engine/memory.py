"""
engine/memory.py
────────────────
Persistent conversation memory and long-term fact store.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("Zenin.Memory")


class MemoryStore:
    """
    Manages two tiers of memory:

    1. Short-term  — sliding window of recent conversation turns.
    2. Long-term   — pinned facts that persist across sessions (user preferences,
                     important context, birthdays, etc.)
    """

    def __init__(self, path: Path, limit: int = 40):
        self._path       = path
        self._limit      = limit          # max turns kept in context
        self._history: list[dict]  = []   # {"role": "user"|"assistant", "content": "..."}
        self._pinned:  list[str]   = []   # persistent facts

    # ── Persistence ────────────────────────────────────────────────────────────

    async def load(self):
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._pinned  = data.get("pinned", [])
                self._history = data.get("history", [])
                log.info(
                    f"Memory loaded — {len(self._history)} turns, "
                    f"{len(self._pinned)} pinned facts."
                )
            except Exception as exc:
                log.warning(f"Could not load memory file: {exc}")

    async def save(self):
        try:
            self._path.write_text(
                json.dumps(
                    {"pinned": self._pinned, "history": self._history[-self._limit:]},
                    indent=2,
                )
            )
        except Exception as exc:
            log.warning(f"Could not save memory: {exc}")

    # ── Short-term memory ──────────────────────────────────────────────────────

    def append(self, role: str, content: str):
        self._history.append({"role": role, "content": content})
        # Trim to limit
        if len(self._history) > self._limit:
            # Keep an even number (pairs) — drop oldest pair
            self._history = self._history[-self._limit:]

    def as_messages(self) -> list[dict]:
        """Return history in the Anthropic messages format."""
        return [{"role": m["role"], "content": m["content"]} for m in self._history]

    def clear_conversation(self):
        self._history.clear()

    # ── Long-term memory ───────────────────────────────────────────────────────

    def pin(self, fact: str):
        if fact not in self._pinned:
            self._pinned.append(fact)

    def unpin(self, index: int):
        if 0 <= index < len(self._pinned):
            removed = self._pinned.pop(index)
            log.info(f"Unpinned fact: {removed}")

    def get_pinned_facts(self) -> list[str]:
        return list(self._pinned)

    def clear_all(self):
        self._history.clear()
        self._pinned.clear()

    # ── Repr ───────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<MemoryStore turns={len(self._history)} "
            f"pinned={len(self._pinned)} limit={self._limit}>"
        )
