"""Bilibili authentication — cookie management.

Supports loading cookies from a JSON file. QR code login can be added
later via the bilibili-api-python library.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

log = structlog.get_logger()

_DEFAULT_COOKIE_PATH = Path.home() / ".tastebud" / "bilibili_cookie.json"


def load_cookie(path: Path | None = None) -> dict[str, str] | None:
    """Load saved Bilibili cookies from a JSON file.

    Returns None if the file does not exist.
    """
    cookie_path = path or _DEFAULT_COOKIE_PATH
    if not cookie_path.exists():
        log.info("bilibili_cookie_not_found", path=str(cookie_path))
        return None
    data = json.loads(cookie_path.read_text(encoding="utf-8"))
    log.info("bilibili_cookie_loaded", path=str(cookie_path), keys=list(data.keys()))
    return data


def save_cookie(cookie: dict[str, str], path: Path | None = None) -> Path:
    """Save Bilibili cookies to a JSON file."""
    cookie_path = path or _DEFAULT_COOKIE_PATH
    cookie_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_path.write_text(
        json.dumps(cookie, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("bilibili_cookie_saved", path=str(cookie_path))
    return cookie_path
