"""Feedback storage and preference learning — per-category.

Storage layout:
    downloads/{category}/feedback_log.jsonl          ← append-only history
    downloads/{category}/{source}/{id}/feedback.json ← per-item latest rating

The log is the source of truth. preferences.json can always be
regenerated from the log via replay().
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from collector.base import TagResult
from collector.storage import DEFAULT_DOWNLOAD_DIR, category_dir, item_dir
from engine.preference import load_preferences, save_preferences

# How much each feedback adjusts tag weights
LEARN_RATE = 0.5


def _log_path(category: str, base_dir: Path | None = None) -> Path:
    return category_dir(category, base_dir) / "feedback_log.jsonl"


def load_feedback(
    category: str, source: str, source_id: str, base_dir: Path | None = None
) -> dict | None:
    """Load feedback for an item. Returns None if no feedback yet."""
    path = item_dir(category, source, source_id, base_dir) / "feedback.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_feedback_log(category: str, base_dir: Path | None = None) -> list[dict]:
    """Load all feedback history entries for a category."""
    path = _log_path(category, base_dir)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def submit_feedback(
    category: str,
    source: str,
    source_id: str,
    rating: str,
    tags: list[TagResult],
    base_dir: Path | None = None,
) -> dict[str, float]:
    """Submit feedback for an item and update category preferences.

    Writes to three places:
    1. {category}/feedback_log.jsonl — append-only category history
    2. {category}/{source}/{id}/feedback.json — per-item latest rating
    3. {category}/preferences.json — updated tag weights

    Returns:
        Updated preferences dict.
    """
    root = base_dir or DEFAULT_DOWNLOAD_DIR
    timestamp = datetime.now(timezone.utc).isoformat()
    tag_names = [t.name for t in tags]
    tag_categories = {t.name: t.category for t in tags}

    # 1. Append to category log
    log_entry = {
        "source": source,
        "source_id": source_id,
        "rating": rating,
        "tags": tag_names,
        "tag_categories": tag_categories,
        "timestamp": timestamp,
    }
    log_path = _log_path(category, root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # 2. Save per-item feedback.json
    idir = item_dir(category, source, source_id, root)
    idir.mkdir(parents=True, exist_ok=True)
    (idir / "feedback.json").write_text(
        json.dumps({"rating": rating, "timestamp": timestamp},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3. Update preferences
    prefs = load_preferences(category, root)
    delta = LEARN_RATE if rating == "like" else -LEARN_RATE
    for tag in tags:
        current = prefs.get(tag.name, 0.0)
        prefs[tag.name] = round(current + delta, 2)
    save_preferences(category, prefs, root)

    return prefs


def replay(
    category: str, base_dir: Path | None = None, learn_rate: float = LEARN_RATE
) -> dict[str, float]:
    """Regenerate preferences.json from the full feedback log.

    Use this after changing the algorithm or learn_rate.
    """
    root = base_dir or DEFAULT_DOWNLOAD_DIR
    entries = load_feedback_log(category, root)

    prefs: dict[str, float] = {}
    for entry in entries:
        delta = learn_rate if entry["rating"] == "like" else -learn_rate
        for tag_name in entry["tags"]:
            current = prefs.get(tag_name, 0.0)
            prefs[tag_name] = round(current + delta, 2)

    save_preferences(category, prefs, root)
    return prefs
