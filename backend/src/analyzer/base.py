"""Base analyzer interface and result structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from collector.base import RawContent, TagResult


@dataclass
class AnalysisResult:
    """Structured analysis of a gallery as a whole.

    Produced by the second layer (deep scan).
    Stored as analysis.json in the gallery directory.
    """

    # Visual style: e.g. "watercolor", "digital", "sketch", "pixel_art"
    style: str = ""

    # Thematic tags: e.g. ["romance", "school_life", "fantasy"]
    theme: list[str] = field(default_factory=list)

    # Overall quality score: 0.0 ~ 1.0
    quality: float = 0.0

    # Mood/atmosphere: e.g. ["warm", "nostalgic", "dark"]
    mood: list[str] = field(default_factory=list)

    # Target audience: e.g. "shounen", "seinen", "shoujo", "general"
    target_audience: str = ""

    # Content warnings: e.g. ["violence", "gore"]
    content_warnings: list[str] = field(default_factory=list)

    # Visual complexity: "simple", "medium", "complex"
    visual_complexity: str = ""

    # Free-text description of the gallery as a whole
    description: str = ""

    # Enriched tags: tags discovered or refined by the analyzer
    # (supplements the source tags from collector)
    enriched_tags: list[TagResult] = field(default_factory=list)


class BaseAnalyzer(ABC):
    """Abstract base for content analyzers.

    An analyzer takes a gallery (metadata + images) and produces
    a structured AnalysisResult that describes the content as a whole.
    """

    @abstractmethod
    async def analyze(
        self, content: RawContent, images_dir: Path | None = None
    ) -> AnalysisResult:
        """Analyze content and return structured analysis.

        Args:
            content: Gallery metadata and tags from the collector.
            images_dir: Path to the gallery's images/ directory.
                        None if images haven't been downloaded.
        """
