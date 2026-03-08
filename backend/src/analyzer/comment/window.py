"""Analysis window — triggers AI analysis when comment count reaches threshold."""

from __future__ import annotations

import json
from pathlib import Path


def _pending_path(base_dir: Path, target_type: str, target_id: str) -> Path:
    return base_dir / target_type / target_id / "comments" / "pending_count.json"


def get_pending_count(
        base_dir: Path, target_type: str, target_id: str
) -> int:
    """Get the number of comments awaiting analysis."""
    path = _pending_path(base_dir, target_type, target_id)
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("count", 0)


def add_pending(
        base_dir: Path, target_type: str, target_id: str, count: int
) -> int:
    """Add to the pending comment counter. Returns new total."""
    current = get_pending_count(base_dir, target_type, target_id)
    new_total = current + count
    path = _pending_path(base_dir, target_type, target_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"count": new_total}, indent=2), encoding="utf-8"
    )
    return new_total


def reset_pending(base_dir: Path, target_type: str, target_id: str) -> None:
    """Reset the pending counter after analysis."""
    path = _pending_path(base_dir, target_type, target_id)
    if path.exists():
        path.write_text(json.dumps({"count": 0}, indent=2), encoding="utf-8")


def should_analyze(
        base_dir: Path, target_type: str, target_id: str, threshold: int
) -> bool:
    """Check if pending count has reached the analysis threshold."""
    return get_pending_count(base_dir, target_type, target_id) >= threshold
