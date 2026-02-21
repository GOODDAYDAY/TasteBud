"""User preference storage — per-category JSON file.

File: downloads/{category}/preferences.json
Format: {"tag_name": weight, ...}

Positive weight = like, negative = dislike.
"""

import json
from pathlib import Path

from collector.storage import DEFAULT_DOWNLOAD_DIR, category_dir


def _pref_path(category: str, base_dir: Path | None = None) -> Path:
    return category_dir(category, base_dir) / "preferences.json"


def load_preferences(category: str, base_dir: Path | None = None) -> dict[str, float]:
    """Load current tag preferences for a category."""
    path = _pref_path(category, base_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_preferences(
    category: str, prefs: dict[str, float], base_dir: Path | None = None
) -> None:
    """Save tag preferences for a category."""
    path = _pref_path(category, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
