"""Filesystem locations shared by the pi extension and the daemon."""

from __future__ import annotations

import os
from pathlib import Path


def root() -> Path:
    return Path(os.environ.get("PI_DECK_HOME", str(Path.home() / ".pi-deck")))


def status_dir() -> Path:
    return root() / "status"


def log_file() -> Path:
    return root() / "pideck.log"


def config_file() -> Path:
    return root() / "config.json"


def ensure_dirs() -> None:
    status_dir().mkdir(parents=True, exist_ok=True)
