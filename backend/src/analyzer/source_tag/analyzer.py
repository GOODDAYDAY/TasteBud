"""Source tag analyzer — baseline analysis from collector tags only.

No model needed. Derives style, theme, mood etc. from the structured
tags that e-hentai (or other sources) already provide.

This serves as the fallback / first-pass analyzer. A VLM-based analyzer
can override or enrich these results later.
"""

from pathlib import Path

from analyzer.base import AnalysisResult, BaseAnalyzer
from collector.base import RawContent, TagResult

# Tag-to-field mapping rules (category -> which AnalysisResult field)
_THEME_CATEGORIES = {"parody", "character"}
_MOOD_TAGS = {
    "dark", "comedy", "horror", "romance", "drama", "wholesome",
    "warm", "melancholy", "cute", "sad", "happy",
}
_STYLE_TAGS = {
    "watercolor", "sketch", "digital", "pixel_art", "monochrome",
    "full_color", "greyscale", "lineart",
}
_WARNING_TAGS = {
    "gore", "guro", "violence", "snuff", "torture", "scat",
}


class SourceTagAnalyzer(BaseAnalyzer):
    """Derives structured analysis purely from existing source tags.

    Normalizes tags, then maps them into the AnalysisResult fields
    based on their category and name.
    """

    async def analyze(
        self, content: RawContent, images_dir: Path | None = None
    ) -> AnalysisResult:
        # Normalize all tags first
        normalized = [
            TagResult(
                name=self._normalize(tag.name),
                category=tag.category,
                confidence=tag.confidence,
            )
            for tag in content.tags
        ]

        # Classify into result fields
        themes: list[str] = []
        moods: list[str] = []
        warnings: list[str] = []
        style = ""

        for tag in normalized:
            if tag.category in _THEME_CATEGORIES:
                themes.append(tag.name)
            if tag.name in _MOOD_TAGS:
                moods.append(tag.name)
            if tag.name in _STYLE_TAGS and not style:
                style = tag.name
            if tag.name in _WARNING_TAGS:
                warnings.append(tag.name)

        # Target audience from e-hentai category metadata
        category = str(content.metadata.get("category", "")).lower()
        audience = self._map_audience(category)

        return AnalysisResult(
            style=style,
            theme=themes,
            quality=self._estimate_quality(content),
            mood=moods,
            target_audience=audience,
            content_warnings=warnings,
            visual_complexity="",  # can't determine from tags alone
            description="",       # needs VLM
            enriched_tags=normalized,
        )

    @staticmethod
    def _normalize(tag_name: str) -> str:
        """Normalize tag name: lowercase, replace spaces with underscores."""
        return tag_name.strip().lower().replace(" ", "_")

    @staticmethod
    def _map_audience(category: str) -> str:
        """Map e-hentai category to target audience."""
        mapping = {
            "doujinshi": "general",
            "manga": "general",
            "artist cg": "general",
            "game cg": "general",
            "non-h": "general",
            "cosplay": "general",
            "image set": "general",
        }
        return mapping.get(category, "")

    @staticmethod
    def _estimate_quality(content: RawContent) -> float:
        """Rough quality estimate from rating metadata."""
        try:
            rating = float(content.metadata.get("rating", 0))
            return round(min(rating / 5.0, 1.0), 2)  # e-hentai rates 0-5
        except (ValueError, TypeError):
            return 0.0
