"""VLM analyzer — visual analysis via local Ollama model.

Analyzes gallery images using a local Vision Language Model (moondream, llava, etc.)
through the Ollama API. Produces structured AnalysisResult with description,
visual tags, quality assessment, and style classification.

Requires Ollama running locally. Gracefully fails if unavailable.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
from typing import TYPE_CHECKING

import httpx

from analyzer.base import AnalysisResult, BaseAnalyzer
from collector.base import RawContent, TagResult

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_SAMPLE_COUNT = 4

_ANALYSIS_PROMPT = """\
Analyze this image from a gallery. Respond in JSON only, no other text:
{
  "description": "one sentence describing the visual content",
  "style": "one of: watercolor, digital, sketch, pixel_art, photograph, mixed",
  "quality": 0.0 to 1.0,
  "mood": ["list", "of", "mood", "words"],
  "visual_complexity": "simple or medium or complex",
  "content_warnings": ["list any warnings or empty list"],
  "visual_tags": ["list", "of", "descriptive", "tags"]
}"""


class VLMAnalyzer(BaseAnalyzer):
    """Analyze images using a local VLM via Ollama API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "moondream",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def analyze(
        self, content: RawContent, images_dir: Path | None = None
    ) -> AnalysisResult:
        if not images_dir or not images_dir.exists():
            logger.warning("No images directory for %s/%s", content.source, content.source_id)
            return AnalysisResult()

        sample_paths = self._pick_samples(images_dir)
        if not sample_paths:
            logger.warning("No images found in %s", images_dir)
            return AnalysisResult()

        # Analyze each sample and merge results
        analyses: list[dict] = []
        for img_path in sample_paths:
            result = await self._analyze_single(img_path)
            if result:
                analyses.append(result)

        if not analyses:
            return AnalysisResult()

        return self._merge_analyses(analyses, content)

    def _pick_samples(self, images_dir: Path) -> list[Path]:
        """Pick evenly-spaced sample images from the gallery."""
        extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
        all_images = sorted(
            p for p in images_dir.iterdir()
            if p.suffix.lower() in extensions
        )
        if not all_images:
            return []

        if len(all_images) <= _SAMPLE_COUNT:
            return all_images

        # Evenly spaced
        step = len(all_images) / _SAMPLE_COUNT
        return [all_images[int(i * step)] for i in range(_SAMPLE_COUNT)]

    async def _analyze_single(self, image_path: Path) -> dict | None:
        """Send a single image to Ollama for analysis."""
        try:
            image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

            payload = {
                "model": self.model,
                "prompt": _ANALYSIS_PROMPT,
                "images": [image_b64],
                "stream": False,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()

            response_text = resp.json().get("response", "")
            return self._parse_response(response_text)

        except httpx.ConnectError:
            logger.warning("Ollama not reachable at %s", self.base_url)
            return None
        except Exception:
            logger.warning("VLM analysis failed for %s", image_path.name, exc_info=True)
            return None

    @staticmethod
    def _parse_response(text: str) -> dict | None:
        """Extract JSON from VLM response text."""
        text = text.strip()

        # Try to find JSON in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            logger.warning("Failed to parse VLM JSON: %s", text[:200])
            return None

    @staticmethod
    def _merge_analyses(analyses: list[dict], content: RawContent) -> AnalysisResult:
        """Merge multiple per-image analyses into one AnalysisResult."""
        # Collect all values
        descriptions: list[str] = []
        styles: list[str] = []
        all_moods: list[str] = []
        all_warnings: list[str] = []
        all_visual_tags: list[str] = []
        qualities: list[float] = []
        complexities: list[str] = []

        for a in analyses:
            if d := a.get("description"):
                descriptions.append(d)
            if s := a.get("style"):
                styles.append(s)
            if m := a.get("mood"):
                all_moods.extend(m if isinstance(m, list) else [m])
            if w := a.get("content_warnings"):
                all_warnings.extend(w if isinstance(w, list) else [w])
            if vt := a.get("visual_tags"):
                all_visual_tags.extend(vt if isinstance(vt, list) else [vt])
            if (q := a.get("quality")) is not None:
                with contextlib.suppress(ValueError, TypeError):
                    qualities.append(float(q))
            if c := a.get("visual_complexity"):
                complexities.append(c)

        # Pick most common style
        style = max(set(styles), key=styles.count) if styles else ""

        # Average quality
        quality = round(sum(qualities) / len(qualities), 2) if qualities else 0.0

        # Most common complexity
        complexity = max(set(complexities), key=complexities.count) if complexities else ""

        # Deduplicate lists
        moods = list(dict.fromkeys(all_moods))
        warnings = list(dict.fromkeys(all_warnings))

        # Build enriched tags from VLM visual_tags + source tags
        enriched_tags = list(content.tags)
        seen = {t.name for t in enriched_tags}
        for vt in dict.fromkeys(all_visual_tags):
            if vt not in seen:
                enriched_tags.append(TagResult(name=vt, category="visual", confidence=0.8))
                seen.add(vt)

        return AnalysisResult(
            style=style,
            theme=[],  # Themes come from source tags, not VLM
            quality=quality,
            mood=moods,
            target_audience="",  # From source tags
            content_warnings=warnings,
            visual_complexity=complexity,
            description="; ".join(descriptions[:3]),
            enriched_tags=enriched_tags,
        )
