"""Rate downloaded items to train your preferences.

Usage:
    python scripts/feedback.py              # rate unrated manga items
    python scripts/feedback.py news         # rate unrated news items
    python scripts/feedback.py manga 3797890 like  # rate a specific item
"""

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from collector.base import TagResult
from collector.storage import category_dir
from engine.feedback import load_feedback, submit_feedback
from engine.preference import load_preferences

DEFAULT_CATEGORY = "manga"


def find_items(category: str) -> list[Path]:
    cat_dir = category_dir(category)
    if not cat_dir.exists():
        return []
    items: list[Path] = []
    for source_dir in cat_dir.iterdir():
        if not source_dir.is_dir() or source_dir.name.endswith(".json"):
            continue
        for item_path in source_dir.iterdir():
            if item_path.is_dir() and (item_path / "data.json").exists():
                items.append(item_path)
    return sorted(items)


def load_tags(item_path: Path) -> list[TagResult]:
    data = json.loads((item_path / "data.json").read_text(encoding="utf-8"))
    return [
        TagResult(name=t["name"], category=t.get("category", "general"))
        for t in data.get("tags", [])
    ]


def get_source_and_id(item_path: Path) -> tuple[str, str]:
    """Extract source and source_id from path: .../{source}/{source_id}"""
    return item_path.parent.name, item_path.name


def show_item(item_path: Path) -> str:
    data = json.loads((item_path / "data.json").read_text(encoding="utf-8"))
    title = data.get("title", "?")
    meta = data.get("metadata", {})

    source, sid = get_source_and_id(item_path)
    print(f"\n  Source:   {source}/{sid}")
    print(f"  Title:    {title}")

    info_parts = []
    for key in ("category", "rating", "filecount"):
        if key in meta:
            info_parts.append(f"{key}: {meta[key]}")
    if info_parts:
        print(f"  Info:     {', '.join(info_parts)}")

    if data.get("url"):
        print(f"  URL:      {data['url']}")

    tags = data.get("tags", [])
    if tags:
        tag_str = ", ".join(t["name"] for t in tags[:15])
        if len(tags) > 15:
            tag_str += f" ... (+{len(tags) - 15} more)"
        print(f"  Tags:     {tag_str}")

    return title


def rate_specific(category: str, source_id: str, rating: str) -> None:
    """Rate a specific item by source_id (searches all sources)."""
    items = find_items(category)
    match = next((i for i in items if i.name == source_id), None)
    if not match:
        print(f"Item {source_id} not found in {category}.")
        return

    show_item(match)
    source, sid = get_source_and_id(match)
    tags = load_tags(match)
    prefs = submit_feedback(category, source, sid, rating, tags)
    print(f"\n  Rated: {rating}")
    print(f"  Preferences updated ({len(prefs)} tags)")


def rate_interactive(category: str) -> None:
    items = find_items(category)
    if not items:
        print(f"No items found in {category}. Download some first.")
        return

    # Filter to unrated
    unrated = []
    for item_path in items:
        source, sid = get_source_and_id(item_path)
        if load_feedback(category, source, sid) is None:
            unrated.append(item_path)

    print(f"Category: {category}")
    print(f"Found {len(items)} items, {len(unrated)} unrated.")

    if not unrated:
        print("All items rated!")
        return

    for item_path in unrated:
        show_item(item_path)
        print("\n  [l]ike  [d]islike  [s]kip  [q]uit")
        cmd = input("  > ").strip().lower()

        source, sid = get_source_and_id(item_path)
        if cmd in ("l", "like"):
            tags = load_tags(item_path)
            submit_feedback(category, source, sid, "like", tags)
            print("  -> liked")
        elif cmd in ("d", "dislike"):
            tags = load_tags(item_path)
            submit_feedback(category, source, sid, "dislike", tags)
            print("  -> disliked")
        elif cmd == "q":
            break
        else:
            print("  -> skipped")

    prefs = load_preferences(category)
    print(f"\nDone. {category} preferences now have {len(prefs)} tags.")


if __name__ == "__main__":
    args = sys.argv[1:]

    if len(args) >= 3:
        # feedback.py <category> <source_id> <rating>
        rate_specific(args[0], args[1], args[2])
    elif len(args) >= 1:
        rate_interactive(args[0])
    else:
        rate_interactive(DEFAULT_CATEGORY)
