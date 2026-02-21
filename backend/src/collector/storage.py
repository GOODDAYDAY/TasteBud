"""Structured storage for collected content.

Each collected item gets a directory like:
    downloads/{source}/{source_id}/
        images/         ← downloaded image files
        tags.txt        ← human-readable tags grouped by category
        data.json       ← raw metadata from the source API
        analysis.json   ← structured analysis result (from analyzer)
        feedback.json   ← user feedback (from engine)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from collector.base import RawContent

if TYPE_CHECKING:
    from analyzer.base import AnalysisResult


DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "downloads"


def gallery_dir(source: str, source_id: str, base_dir: Path | None = None) -> Path:
    """Return the storage directory for a gallery."""
    root = base_dir or DEFAULT_DOWNLOAD_DIR
    return root / source / source_id


def save_metadata(content: RawContent, base_dir: Path | None = None) -> Path:
    """Save tags.txt and data.json for a collected gallery.

    Returns the gallery directory path.
    """
    gdir = gallery_dir(content.source, content.source_id, base_dir)
    gdir.mkdir(parents=True, exist_ok=True)

    # data.json — raw metadata
    data = {
        "source": content.source,
        "source_id": content.source_id,
        "title": content.title,
        "url": content.url,
        "thumbnail_url": content.thumbnail_url,
        "metadata": content.metadata,
        "tags": [
            {"name": t.name, "category": t.category, "confidence": t.confidence}
            for t in content.tags
        ],
    }
    (gdir / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # tags.txt — human-readable, grouped by category
    by_category: dict[str, list[str]] = {}
    for tag in content.tags:
        by_category.setdefault(tag.category, []).append(tag.name)

    lines: list[str] = []
    for category, names in sorted(by_category.items()):
        lines.append(f"[{category}]")
        for name in sorted(names):
            lines.append(f"  {name}")
        lines.append("")
    (gdir / "tags.txt").write_text("\n".join(lines), encoding="utf-8")

    return gdir


def images_dir(source: str, source_id: str, base_dir: Path | None = None) -> Path:
    """Return (and create) the images subdirectory for a gallery."""
    img_dir = gallery_dir(source, source_id, base_dir) / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    return img_dir


def save_analysis(
    source: str, source_id: str, result: AnalysisResult, base_dir: Path | None = None
) -> Path:
    """Save analysis.json for a gallery. Returns the file path."""
    gdir = gallery_dir(source, source_id, base_dir)
    gdir.mkdir(parents=True, exist_ok=True)

    data = asdict(result)
    # Convert TagResult objects to plain dicts
    data["enriched_tags"] = [
        {"name": t.name, "category": t.category, "confidence": t.confidence}
        for t in result.enriched_tags
    ]

    path = gdir / "analysis.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_analysis(
    source: str, source_id: str, base_dir: Path | None = None
) -> dict | None:
    """Load analysis.json for a gallery. Returns None if not analyzed yet."""
    path = gallery_dir(source, source_id, base_dir) / "analysis.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
