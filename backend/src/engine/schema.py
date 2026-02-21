"""Category schema — defines evaluation dimensions for a content category.

File: downloads/{category}/schema.json

Each category declares its own analysis fields, so analyzers and scorers
know what dimensions to evaluate.
"""

import json
from pathlib import Path

from collector.storage import DEFAULT_DOWNLOAD_DIR, category_dir

# Built-in schemas for common categories
BUILTIN_SCHEMAS: dict[str, dict] = {
    "manga": {
        "name": "manga",
        "description": "Comics and manga",
        "dimensions": {
            "style": {"type": "str", "description": "Art style (e.g. watercolor, digital)"},
            "theme": {"type": "list[str]", "description": "Themes (e.g. romance, fantasy)"},
            "quality": {"type": "float", "description": "Overall quality 0.0~1.0"},
            "mood": {"type": "list[str]", "description": "Mood/atmosphere"},
            "target_audience": {"type": "str", "description": "Target audience"},
            "content_warnings": {"type": "list[str]", "description": "Content warnings"},
            "visual_complexity": {"type": "str", "description": "simple/medium/complex"},
            "description": {"type": "str", "description": "Overall description"},
        },
    },
    "news": {
        "name": "news",
        "description": "News articles",
        "dimensions": {
            "domain": {"type": "str", "description": "News domain (tech, politics, etc.)"},
            "depth": {"type": "str", "description": "shallow/medium/deep"},
            "timeliness": {"type": "str", "description": "breaking/recent/evergreen"},
            "stance": {"type": "str", "description": "neutral/left/right/opinion"},
            "quality": {"type": "float", "description": "Overall quality 0.0~1.0"},
            "description": {"type": "str", "description": "Summary"},
        },
    },
}


def load_schema(category: str, base_dir: Path | None = None) -> dict | None:
    """Load the schema for a category. Returns None if not defined."""
    path = category_dir(category, base_dir) / "schema.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return BUILTIN_SCHEMAS.get(category)


def save_schema(category: str, schema: dict, base_dir: Path | None = None) -> Path:
    """Save a schema for a category. Returns the file path."""
    cdir = category_dir(category, base_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / "schema.json"
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def init_category(category: str, base_dir: Path | None = None) -> Path:
    """Initialize a category directory with its schema.

    Uses built-in schema if available, otherwise creates a minimal one.
    """
    cdir = category_dir(category, base_dir)
    cdir.mkdir(parents=True, exist_ok=True)

    schema_path = cdir / "schema.json"
    if not schema_path.exists():
        schema = BUILTIN_SCHEMAS.get(category, {
            "name": category,
            "description": f"Custom category: {category}",
            "dimensions": {},
        })
        save_schema(category, schema, base_dir)

    return cdir
