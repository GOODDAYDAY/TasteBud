"""Three-layer sieve pipeline: quick sieve -> deep scan -> user evaluation.

Layer 1 (Quick Sieve): Tag scoring + optional CLIP similarity on thumbnail.
Layer 2 (Deep Scan): VLM analysis via Ollama on downloaded images.
Layer 3 (User Evaluation): Human like/dislike rating.

All layer results are stored in a single sieve.json per item.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from collector.storage import item_dir

if TYPE_CHECKING:
    from collector.base import RawContent

logger = logging.getLogger(__name__)


@dataclass
class LayerResult:
    """Result from a single sieve layer."""

    passed: bool
    score: float
    threshold: float
    timestamp: str = ""
    details: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class SieveResult:
    """Combined result from all three sieve layers."""

    layer1: LayerResult | None = None
    layer2: LayerResult | None = None
    layer3: LayerResult | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.layer1:
            result["layer1"] = asdict(self.layer1)
        if self.layer2:
            result["layer2"] = asdict(self.layer2)
        if self.layer3:
            result["layer3"] = asdict(self.layer3)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> SieveResult:
        result = cls()
        if "layer1" in data:
            d = data["layer1"]
            assert isinstance(d, dict)
            result.layer1 = LayerResult(**d)  # type: ignore[arg-type]
        if "layer2" in data:
            d = data["layer2"]
            assert isinstance(d, dict)
            result.layer2 = LayerResult(**d)  # type: ignore[arg-type]
        if "layer3" in data:
            d = data["layer3"]
            assert isinstance(d, dict)
            result.layer3 = LayerResult(**d)  # type: ignore[arg-type]
        return result


# ── Persistence ──────────────────────────────────────────────────────


def save_sieve(
    category: str,
    source: str,
    source_id: str,
    result: SieveResult,
    base_dir: Path | None = None,
) -> Path:
    """Save sieve.json for an item. Returns the file path."""
    idir = item_dir(category, source, source_id, base_dir)
    idir.mkdir(parents=True, exist_ok=True)
    path = idir / "sieve.json"
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_sieve(
    category: str,
    source: str,
    source_id: str,
    base_dir: Path | None = None,
) -> SieveResult | None:
    """Load sieve.json for an item. Returns None if not sieved yet."""
    path = item_dir(category, source, source_id, base_dir) / "sieve.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SieveResult.from_dict(data)


# ── Layer 1: Quick Sieve ─────────────────────────────────────────────


async def run_layer1(
    content: RawContent,
    preferences: dict[str, float],
    threshold: float,
    clip_baseline: list[float] | None = None,
) -> LayerResult:
    """Tag scoring + optional CLIP similarity on thumbnail.

    CLIP is optional — if not installed or no baseline, falls back to tag-only scoring.
    Final score = weighted average of tag_score and clip_score (if available).
    """
    from engine.scorer import TagScorer

    scorer = TagScorer()
    tag_score_raw, matched = scorer.score(preferences, content.tags)

    # Normalize tag score to 0-1 range via sigmoid-like mapping
    tag_score = _normalize_tag_score(tag_score_raw)

    clip_score: float | None = None

    if clip_baseline and content.thumbnail_url:
        clip_score = await _try_clip_score(content.thumbnail_url, clip_baseline)

    # Combine scores
    combined = 0.5 * tag_score + 0.5 * clip_score if clip_score is not None else tag_score

    combined = round(combined, 4)
    passed = combined >= threshold

    details: dict[str, object] = {
        "tag_score": round(tag_score, 4),
        "tag_score_raw": tag_score_raw,
        "matched_tags": matched,
    }
    if clip_score is not None:
        details["clip_score"] = round(clip_score, 4)

    return LayerResult(
        passed=passed,
        score=combined,
        threshold=threshold,
        details=details,
    )


async def _try_clip_score(
    thumbnail_url: str, baseline: list[float]
) -> float | None:
    """Try to compute CLIP similarity. Returns None if CLIP unavailable."""
    try:
        from analyzer.clip.analyzer import CLIPAnalyzer
    except ImportError:
        return None

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(thumbnail_url)
            if resp.status_code != 200:
                return None

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(resp.content)
            tmp_path = Path(f.name)

        try:
            analyzer = CLIPAnalyzer()
            embedding = analyzer.embed_image(tmp_path)
            return analyzer.similarity(embedding, baseline)
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.warning("CLIP scoring failed, falling back to tag-only", exc_info=True)
        return None


def _normalize_tag_score(raw: float) -> float:
    """Normalize raw tag score to 0-1 range.

    Uses a simple sigmoid: 1 / (1 + exp(-raw)).
    Raw=0 -> 0.5, positive raw -> >0.5, negative raw -> <0.5.
    """
    import math

    return round(1.0 / (1.0 + math.exp(-raw)), 4)


# ── Layer 2: Deep Scan ───────────────────────────────────────────────


async def run_layer2(
    content: RawContent,
    images_dir: Path,
    threshold: float,
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "moondream",
) -> LayerResult:
    """VLM analysis via Ollama. Produces detailed visual analysis.

    If Ollama is not running, returns a skip result (passed=True, score=0)
    so the pipeline doesn't block.
    """
    try:
        from analyzer.vlm.analyzer import VLMAnalyzer

        analyzer = VLMAnalyzer(base_url=ollama_base_url, model=ollama_model)
        analysis = await analyzer.analyze(content, images_dir)

        # Score from VLM quality assessment
        score = analysis.quality

        # Boost/penalize based on content warnings
        if analysis.content_warnings:
            score *= 0.7

        score = round(score, 4)
        passed = score >= threshold

        return LayerResult(
            passed=passed,
            score=score,
            threshold=threshold,
            details={
                "model": ollama_model,
                "description": analysis.description,
                "style": analysis.style,
                "visual_complexity": analysis.visual_complexity,
            },
        )
    except Exception as e:
        logger.warning("Layer 2 (VLM) failed: %s — skipping", e)
        return LayerResult(
            passed=True,
            score=0.0,
            threshold=threshold,
            details={"skipped": True, "reason": str(e)},
        )


# ── Layer 3: record user feedback into sieve ─────────────────────────


def record_layer3(rating: str) -> LayerResult:
    """Create a Layer 3 result from user feedback."""
    return LayerResult(
        passed=rating == "like",
        score=1.0 if rating == "like" else 0.0,
        threshold=0.0,
        details={"rating": rating},
    )
