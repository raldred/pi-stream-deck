"""Filesystem locations shared by the pi extension and the daemon."""

from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    """Return the shared data directory, respecting Pi's configured agent dir."""
    if override := os.environ.get("PI_DECK_HOME"):
        return Path(override)
    agent_dir = Path(os.environ.get(
        "PI_CODING_AGENT_DIR", str(Path.home() / ".pi" / "agent")))
    return agent_dir / "pi-stream-deck"


def status_dir() -> Path:
    return root() / "status"


def log_file() -> Path:
    return root() / "pideck.log"


def config_file() -> Path:
    return root() / "config.json"


def ensure_dirs() -> None:
    status_dir().mkdir(parents=True, exist_ok=True)
