"""
engine/config.py
────────────────
Central configuration for Zenin Assistant.
Edit the values below or set environment variables prefixed with ZENIN_.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

_CFG_FILE = Path(__file__).parent.parent / "zenin_config.json"


@dataclass
class Config:
    # ── Identity ───────────────────────────────────────────────────
    assistant_name: str = "Zenin"
    owner_name: str = "Boss"

    # ── AI provider ────────────────────────────────────────────────
    anthropic_api_key: str = ""          # set via env ANTHROPIC_API_KEY
    model: str = "claude-opus-4-5"
    max_tokens: int = 2048
    temperature: float = 0.7

    # ── Personality ────────────────────────────────────────────────
    persona: str = (
        "You are Zenin, an elite personal AI assistant — think JARVIS from Iron Man. "
        "You are sharp, precise, loyal, and occasionally dry-witted. "
        "You address the user as '{owner}'. "
        "You speak confidently, never hedge unnecessarily. "
        "You proactively surface relevant information without being asked. "
        "Keep responses concise unless depth is required. "
        "You have access to tools (web search, system info, reminders, notes) "
        "and use them silently in the background before answering. "
        "Never break character."
    )

    # ── Server ─────────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 7474

    # ── Features ───────────────────────────────────────────────────
    enable_voice: bool = False           # TTS/STT (requires extra deps)
    enable_web_search: bool = True
    memory_limit: int = 40              # conversation turns kept in context

    # ── Paths ──────────────────────────────────────────────────────
    notes_dir: Path = field(default_factory=lambda: Path.home() / ".zenin" / "notes")
    memory_file: Path = field(default_factory=lambda: Path.home() / ".zenin" / "memory.json")

    # ── Internal ───────────────────────────────────────────────────
    debug: bool = False

    # ──────────────────────────────────────────────────────────────
    @classmethod
    def load(cls) -> "Config":
        data: dict = {}

        # 1. File-based config
        if _CFG_FILE.exists():
            with open(_CFG_FILE) as f:
                data = json.load(f)

        cfg = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

        # 2. Environment overrides
        cfg.anthropic_api_key = (
            os.environ.get("ANTHROPIC_API_KEY") or cfg.anthropic_api_key
        )
        cfg.owner_name = os.environ.get("ZENIN_OWNER", cfg.owner_name)
        cfg.port       = int(os.environ.get("ZENIN_PORT", cfg.port))
        cfg.debug      = os.environ.get("ZENIN_DEBUG", "").lower() in ("1", "true", "yes")

        # 3. Inject owner name into persona
        cfg.persona = cfg.persona.replace("{owner}", cfg.owner_name)

        # 4. Ensure directories exist
        cfg.notes_dir.mkdir(parents=True, exist_ok=True)
        cfg.memory_file.parent.mkdir(parents=True, exist_ok=True)

        return cfg

    def save(self):
        data = asdict(self)
        # Convert Paths to strings for JSON serialisation
        data["notes_dir"]    = str(data["notes_dir"])
        data["memory_file"]  = str(data["memory_file"])
        with open(_CFG_FILE, "w") as f:
            json.dump(data, f, indent=2)
