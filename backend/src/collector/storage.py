"""Structured storage for collected content.

Directory layout:
    downloads/{category}/
        schema.json                 ← defines evaluation dimensions for this category
        preferences.json            ← user preferences for this category
        feedback_log.jsonl          ← feedback history for this category
        {source}/{source_id}/
            data.json               ← raw metadata from source API
            tags.txt                ← human-readable tags
            images/                 ← downloaded files
            download.json           ← download completion marker (written on success)
            analysis.json           ← structured analysis result
            feedback.json           ← per-item user feedback
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from collector.base import RawContent, TagResult

if TYPE_CHECKING:
    from analyzer.base import AnalysisResult


DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "downloads"


def category_dir(category: str, base_dir: Path | None = None) -> Path:
    """Return the root directory for a content category."""
    return (base_dir or DEFAULT_DOWNLOAD_DIR) / category


def item_dir(
    category: str, source: str, source_id: str, base_dir: Path | None = None
) -> Path:
    """Return the storage directory for a content item."""
    return category_dir(category, base_dir) / source / source_id


def save_metadata(
    content: RawContent, category: str, base_dir: Path | None = None
) -> Path:
    """Save data.json and tags.txt for a collected item.

    Returns the item directory path.
    """
    idir = item_dir(category, content.source, content.source_id, base_dir)
    idir.mkdir(parents=True, exist_ok=True)

    # data.json
    data = {
        "source": content.source,
        "source_id": content.source_id,
        "category": category,
        "title": content.title,
        "url": content.url,
        "thumbnail_url": content.thumbnail_url,
        "metadata": content.metadata,
        "tags": [
            {"name": t.name, "category": t.category, "confidence": t.confidence}
            for t in content.tags
        ],
    }
    (idir / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # tags.txt
    by_cat: dict[str, list[str]] = {}
    for tag in content.tags:
        by_cat.setdefault(tag.category, []).append(tag.name)

    lines: list[str] = []
    for cat, names in sorted(by_cat.items()):
        lines.append(f"[{cat}]")
        for name in sorted(names):
            lines.append(f"  {name}")
        lines.append("")
    (idir / "tags.txt").write_text("\n".join(lines), encoding="utf-8")

    return idir


def images_dir(
    category: str, source: str, source_id: str, base_dir: Path | None = None
) -> Path:
    """Return (and create) the images subdirectory for an item."""
    img_dir = item_dir(category, source, source_id, base_dir) / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def save_analysis(
    category: str,
    source: str,
    source_id: str,
    result: AnalysisResult,
    base_dir: Path | None = None,
) -> Path:
    """Save analysis.json for an item. Returns the file path."""
    idir = item_dir(category, source, source_id, base_dir)
    idir.mkdir(parents=True, exist_ok=True)

    data = asdict(result)
    data["enriched_tags"] = [
        {"name": t.name, "category": t.category, "confidence": t.confidence}
        for t in result.enriched_tags
    ]

    path = idir / "analysis.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_analysis(
    category: str, source: str, source_id: str, base_dir: Path | None = None
) -> dict | None:
    """Load analysis.json for an item. Returns None if not analyzed yet."""
    path = item_dir(category, source, source_id, base_dir) / "analysis.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_item(item_path: Path) -> RawContent | None:
    """Load a saved item's data.json back into RawContent.

    Args:
        item_path: Directory containing data.json (e.g. downloads/manga/source/123/).
    """
    data_file = item_path / "data.json"
    if not data_file.exists():
        return None

    data = json.loads(data_file.read_text(encoding="utf-8"))
    tags = [
        TagResult(
            name=t["name"],
            category=t.get("category", "general"),
            confidence=t.get("confidence", 1.0),
        )
        for t in data.get("tags", [])
    ]
    return RawContent(
        source=data["source"],
        source_id=data["source_id"],
        title=data.get("title", ""),
        url=data.get("url", ""),
        thumbnail_url=data.get("thumbnail_url", ""),
        tags=tags,
        metadata=data.get("metadata", {}),
    )


def find_items(category: str, base_dir: Path | None = None) -> list[Path]:
    """Find all item directories under a category (any source).

    Returns sorted list of paths that contain data.json.
    """
    cat_dir = category_dir(category, base_dir)
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


def save_download_result(
    category: str,
    source: str,
    source_id: str,
    downloaded: int,
    skipped: int,
    failed: int,
    base_dir: Path | None = None,
) -> Path:
    """Write download.json as completion marker. Returns the file path."""
    from datetime import datetime, timezone

    idir = item_dir(category, source, source_id, base_dir)
    idir.mkdir(parents=True, exist_ok=True)

    data = {
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    path = idir / "download.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def is_downloaded(item_path: Path) -> bool:
    """Check if an item has been fully downloaded (has download.json)."""
    return (item_path / "download.json").exists()


def find_downloaded(category: str, base_dir: Path | None = None) -> list[Path]:
    """Find items that have download.json (completed downloads)."""
    return [p for p in find_items(category, base_dir) if is_downloaded(p)]


def find_unanalyzed(category: str, base_dir: Path | None = None) -> list[Path]:
    """Find items that have data.json but no analysis.json."""
    return [p for p in find_items(category, base_dir) if not (p / "analysis.json").exists()]


# ── Sieve helpers ────────────────────────────────────────────────────


def save_sieve_file(
    category: str,
    source: str,
    source_id: str,
    result: dict,
    base_dir: Path | None = None,
) -> Path:
    """Save sieve.json for an item. Returns the file path."""
    idir = item_dir(category, source, source_id, base_dir)
    idir.mkdir(parents=True, exist_ok=True)
    path = idir / "sieve.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def load_sieve_file(
    category: str,
    source: str,
    source_id: str,
    base_dir: Path | None = None,
) -> dict | None:
    """Load sieve.json for an item. Returns None if not sieved yet."""
    path = item_dir(category, source, source_id, base_dir) / "sieve.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def find_sieved(
    category: str,
    layer: int,
    passed: bool,
    base_dir: Path | None = None,
) -> list[Path]:
    """Find items by sieve status.

    e.g. find_sieved('manga', 1, True) = items that passed layer 1.
    """
    key = f"layer{layer}"
    results: list[Path] = []
    for item_path in find_items(category, base_dir):
        sieve_path = item_path / "sieve.json"
        if not sieve_path.exists():
            continue
        data = json.loads(sieve_path.read_text(encoding="utf-8"))
        layer_data = data.get(key)
        if layer_data and layer_data.get("passed") is passed:
            results.append(item_path)
    return sorted(results)
