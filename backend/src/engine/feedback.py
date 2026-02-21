"""Feedback storage and preference learning.

Each gallery gets a feedback.json:
    downloads/ehentai/{gid}/feedback.json
    {"rating": "like", "timestamp": "2025-01-01T12:00:00"}

When feedback is submitted, preferences.json is updated:
- "like"    → boost all tags in this content by +LEARN_RATE
- "dislike" → penalize all tags by -LEARN_RATE
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from collector.base import TagResult
from collector.storage import DEFAULT_DOWNLOAD_DIR, gallery_dir
from engine.preference import load_preferences, save_preferences

# How much each feedback adjusts tag weights
LEARN_RATE = 0.5


def load_feedback(
    source: str, source_id: str, base_dir: Path | None = None
) -> dict | None:
    """Load feedback for a gallery. Returns None if no feedback yet."""
    path = gallery_dir(source, source_id, base_dir) / "feedback.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def submit_feedback(
    source: str,
    source_id: str,
    rating: str,
    tags: list[TagResult],
    base_dir: Path | None = None,
) -> dict[str, float]:
    """Submit feedback for a gallery and update preferences.

    Args:
        source: Content source (e.g. "ehentai")
        source_id: Gallery ID
        rating: "like" or "dislike"
        tags: The tags of this content
        base_dir: Override download directory

    Returns:
        Updated preferences dict.
    """
    root = base_dir or DEFAULT_DOWNLOAD_DIR

    # Save feedback.json in gallery dir
    gdir = gallery_dir(source, source_id, root)
    gdir.mkdir(parents=True, exist_ok=True)

    feedback = {
        "rating": rating,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    (gdir / "feedback.json").write_text(
        json.dumps(feedback, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Update preferences
    prefs = load_preferences(root)
    delta = LEARN_RATE if rating == "like" else -LEARN_RATE

    for tag in tags:
        current = prefs.get(tag.name, 0.0)
        prefs[tag.name] = round(current + delta, 2)

    save_preferences(prefs, root)
    return prefs
