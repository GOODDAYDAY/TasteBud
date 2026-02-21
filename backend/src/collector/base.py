"""Base collector interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class TagResult:
    """A tag extracted from content."""

    name: str
    category: str = "general"
    confidence: float = 1.0


@dataclass
class RawContent:
    """Raw content fetched from an external source."""

    source: str
    source_id: str
    title: str = ""
    url: str = ""
    thumbnail_url: str = ""
    tags: list[TagResult] = field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)


class BaseCollector(ABC):
    """Abstract base for content collectors."""

    # Each collector declares its content category and source name.
    # These determine the storage path: downloads/{category}/{source}/{id}/
    category: str  # e.g. "manga", "news"
    source: str    # e.g. "ehentai", "rss"

    @abstractmethod
    async def collect(self, **kwargs: str | int) -> list[RawContent]:
        """Fetch content from the external source."""

    @abstractmethod
    def parse_tags(self, raw: RawContent, **kwargs: object) -> list[TagResult]:
        """Extract structured tags from raw content."""
