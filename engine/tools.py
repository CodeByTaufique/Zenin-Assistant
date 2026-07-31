"""
engine/tools.py
───────────────
Zenin's background-intelligence toolkit.
Tools run silently and return enrichment context injected into the prompt.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import platform
import re
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Optional

log = logging.getLogger("Zenin.Tools")


class ToolRegistry:
    """
    Decides which tools to invoke based on the user's message,
    runs them concurrently, and returns a consolidated enrichment string.
    """

    def __init__(self, cfg):
        self.cfg   = cfg
        self._note_store = NoteStore(cfg.notes_dir)

    async def enrich(self, message: str) -> str:
        """Analyse message and gather background context."""
        tasks = []
        msg = message.lower()

        if _needs_time(msg):
            tasks.append(_get_datetime())
        if _needs_system(msg):
            tasks.append(_get_system_info())
        if _needs_notes(msg):
            tasks.append(self._note_store.list_notes())
        if _needs_weather(msg):
            tasks.append(_stub("weather", "Weather lookup requires an API key (OpenWeatherMap). Set WEATHER_API_KEY."))

        if not tasks:
            return ""

        results = await asyncio.gather(*tasks, return_exceptions=True)
        parts = []
        for r in results:
            if isinstance(r, Exception):
                log.debug(f"Tool error: {r}")
            elif r:
                parts.append(str(r))

        return "\n\n".join(parts)

    # ── Note operations (called directly from server) ──────────────────────────

    def save_note(self, title: str, content: str) -> str:
        return self._note_store.save(title, content)

    def get_note(self, title: str) -> Optional[str]:
        return self._note_store.get(title)

    def list_note_titles(self) -> list[str]:
        return self._note_store.titles()

    def delete_note(self, title: str) -> bool:
        return self._note_store.delete(title)


# ── Heuristics ─────────────────────────────────────────────────────────────────

def _needs_time(msg: str) -> bool:
    return any(w in msg for w in ("time", "date", "day", "today", "tomorrow", "schedule", "when"))

def _needs_system(msg: str) -> bool:
    return any(w in msg for w in ("system", "cpu", "memory", "ram", "disk", "battery", "computer", "machine", "specs"))

def _needs_notes(msg: str) -> bool:
    return any(w in msg for w in ("note", "notes", "remind", "reminder", "saved"))

def _needs_weather(msg: str) -> bool:
    return any(w in msg for w in ("weather", "rain", "sunny", "temperature", "forecast", "humidity"))


# ── Tool implementations ───────────────────────────────────────────────────────

async def _get_datetime() -> str:
    now = datetime.datetime.now()
    return (
        f"[DATETIME]\n"
        f"Full: {now.strftime('%A, %d %B %Y at %H:%M:%S')}\n"
        f"ISO:  {now.isoformat()}\n"
        f"Unix: {int(now.timestamp())}"
    )

async def _get_system_info() -> str:
    info = {
        "OS":          f"{platform.system()} {platform.release()}",
        "Hostname":    socket.gethostname(),
        "Python":      platform.python_version(),
        "Architecture":platform.machine(),
        "Processor":   platform.processor() or "Unknown",
    }

    # Try to get CPU usage via psutil if available
    try:
        import psutil
        info["CPU Usage"]    = f"{psutil.cpu_percent(interval=0.1):.1f}%"
        mem = psutil.virtual_memory()
        info["RAM"]          = f"{mem.used // (1024**2)} MB used / {mem.total // (1024**2)} MB total"
        disk = psutil.disk_usage("/")
        info["Disk"]         = f"{disk.used // (1024**3)} GB used / {disk.total // (1024**3)} GB total"
        bat = psutil.sensors_battery()
        if bat:
            info["Battery"]  = f"{bat.percent:.0f}% {'(charging)' if bat.power_plugged else '(on battery)'}"
    except ImportError:
        info["Note"] = "Install psutil for detailed system metrics: pip install psutil"

    lines = "\n".join(f"  {k}: {v}" for k, v in info.items())
    return f"[SYSTEM INFO]\n{lines}"

async def _stub(name: str, message: str) -> str:
    return f"[{name.upper()}]\n  {message}"


# ── Note store ─────────────────────────────────────────────────────────────────

class NoteStore:
    def __init__(self, directory: Path):
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, title: str) -> Path:
        safe = re.sub(r"[^\w\-]", "_", title.lower())
        return self._dir / f"{safe}.json"

    def save(self, title: str, content: str) -> str:
        note = {
            "id":       str(uuid.uuid4()),
            "title":    title,
            "content":  content,
            "created":  datetime.datetime.now().isoformat(),
        }
        self._path(title).write_text(json.dumps(note, indent=2))
        return note["id"]

    def get(self, title: str) -> Optional[dict]:
        p = self._path(title)
        if p.exists():
            return json.loads(p.read_text())
        return None

    def titles(self) -> list[str]:
        return [
            json.loads(f.read_text()).get("title", f.stem)
            for f in sorted(self._dir.glob("*.json"))
        ]

    def delete(self, title: str) -> bool:
        p = self._path(title)
        if p.exists():
            p.unlink()
            return True
        return False

    async def list_notes(self) -> str:
        titles = self.titles()
        if not titles:
            return ""
        return f"[SAVED NOTES]\n" + "\n".join(f"  • {t}" for t in titles)
