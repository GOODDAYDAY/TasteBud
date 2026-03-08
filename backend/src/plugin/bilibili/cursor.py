"""Incremental cursor management for Bilibili comment collection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from plugin.bilibili.models import Cursor


def _cursor_path(base_dir: Path, target_type: str, target_id: str) -> Path:
    return base_dir / target_type / target_id / "comments" / "cursor.json"


def load_cursor(
        base_dir: Path, target_type: str, target_id: str
) -> Cursor:
    """Load cursor from disk, or return a fresh one."""
    path = _cursor_path(base_dir, target_type, target_id)
    if not path.exists():
        return Cursor()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Cursor(
        last_rpid=data.get("last_rpid", 0),
        last_page=data.get("last_page", 0),
        updated_at=data.get("updated_at", ""),
    )


def save_cursor(
        base_dir: Path, target_type: str, target_id: str, cursor: Cursor
) -> Path:
    """Persist cursor to disk."""
    path = _cursor_path(base_dir, target_type, target_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    cursor.updated_at = datetime.now(timezone.utc).isoformat()
    data = {
        "last_rpid": cursor.last_rpid,
        "last_page": cursor.last_page,
        "updated_at": cursor.updated_at,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
