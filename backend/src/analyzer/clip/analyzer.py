"""CLIP embedding analyzer — optional Layer 1 enhancement.

Computes CLIP embeddings for images and compares against a "taste baseline"
(mean embedding of liked items). Provides visual similarity scoring without
needing a heavy VLM.

Requires: sentence-transformers (optional dependency).
Install via: pip install 'tastebud[clip]'
"""

from __future__ import annotations

import json
import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class CLIPAnalyzer:
    """Compute CLIP embedding for an image, compare to taste baseline."""

    def __init__(self, model_name: str = "clip-ViT-B-32") -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed_image(self, image_path: Path) -> list[float]:
        """Compute CLIP embedding for a single image."""
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        embedding = self.model.encode(img)
        return embedding.tolist()

    @staticmethod
    def similarity(embedding: list[float], baseline: list[float]) -> float:
        """Cosine similarity between two embeddings. Returns 0-1."""
        dot = sum(a * b for a, b in zip(embedding, baseline, strict=True))
        norm_a = math.sqrt(sum(a * a for a in embedding))
        norm_b = math.sqrt(sum(b * b for b in baseline))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        cos_sim = dot / (norm_a * norm_b)
        # Map from [-1, 1] to [0, 1]
        return round((cos_sim + 1.0) / 2.0, 4)

    @staticmethod
    def update_baseline(liked_embeddings: list[list[float]]) -> list[float]:
        """Compute taste baseline as mean of liked embeddings."""
        if not liked_embeddings:
            return []
        dim = len(liked_embeddings[0])
        mean = [0.0] * dim
        for emb in liked_embeddings:
            for i, v in enumerate(emb):
                mean[i] += v
        n = len(liked_embeddings)
        return [round(v / n, 6) for v in mean]


def load_baseline(category: str, base_dir: Path | None = None) -> list[float] | None:
    """Load CLIP taste baseline for a category. Returns None if not computed yet."""
    from collector.storage import DEFAULT_DOWNLOAD_DIR, category_dir

    path = category_dir(category, base_dir or DEFAULT_DOWNLOAD_DIR) / "clip_baseline.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("baseline")


def save_baseline(
    category: str, baseline: list[float], base_dir: Path | None = None
) -> Path:
    """Save CLIP taste baseline for a category."""
    from collector.storage import DEFAULT_DOWNLOAD_DIR, category_dir

    path = category_dir(category, base_dir or DEFAULT_DOWNLOAD_DIR) / "clip_baseline.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"baseline": baseline}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
