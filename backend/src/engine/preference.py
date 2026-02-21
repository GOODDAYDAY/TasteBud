"""User preference storage — simple JSON file.

File: downloads/preferences.json
Format: {"tag_name": weight, ...}

Positive weight = like, negative = dislike.
"""

import json
from pathlib import Path

from collector.storage import DEFAULT_DOWNLOAD_DIR


def _pref_path(base_dir: Path | None = None) -> Path:
    return (base_dir or DEFAULT_DOWNLOAD_DIR) / "preferences.json"


def load_preferences(base_dir: Path | None = None) -> dict[str, float]:
    """Load current tag preferences. Returns empty dict if file doesn't exist."""
    path = _pref_path(base_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_preferences(prefs: dict[str, float], base_dir: Path | None = None) -> None:
    """Save tag preferences to disk."""
    path = _pref_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
