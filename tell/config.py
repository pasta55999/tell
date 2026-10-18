"""Runtime configuration. Everything is optional; defaults work offline."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEMO_DIR = DATA_DIR / "demo"
EXPORT_DIR = PROJECT_ROOT / "exports"

APP_NAME = "Tell"
TAGLINE = "Every business has a tell."
DEFAULT_CURRENCY = "AED"


def db_path() -> Path:
    raw = os.environ.get("TELL_DB_PATH")
    path = Path(raw).expanduser() if raw else DATA_DIR / "tell.db"
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def max_upload_mb() -> int:
    try:
        return max(1, int(os.environ.get("TELL_MAX_UPLOAD_MB", "25")))
    except ValueError:
        return 25
