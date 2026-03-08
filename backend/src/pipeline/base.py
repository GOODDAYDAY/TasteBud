"""Base plugin interface for platform-specific pipeline logic."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from analyzer.comment.models import CommentAnalysisResult
    from core.comment import Comment, CommentBatch
    from pipeline.models import PipelineConfig


class BasePlugin(ABC):
    """Abstract base for platform plugins.

    Each platform (bilibili, youtube, etc.) implements this interface
    to provide platform-specific collection, notification rendering,
    and data serialization logic.
    """

    @abstractmethod
    async def collect(
            self, config: PipelineConfig, base_dir: Path
    ) -> list[CommentBatch]:
        """Collect comments from the platform."""

    @abstractmethod
    def render_notification(
            self, result: CommentAnalysisResult
    ) -> tuple[str, str]:
        """Render analysis result as (title, body) for notification."""

    @abstractmethod
    def serialize_batch(self, batch: CommentBatch) -> dict:
        """Serialize a comment batch to a JSON-compatible dict."""

    @abstractmethod
    def deserialize_comments(self, data: dict) -> list[Comment]:
        """Deserialize comments from a stored batch dict."""

    async def ensure_auth(self, config: PipelineConfig) -> bool:
        """Check auth status; prompt login if needed. Returns True if ready."""
        return True

    def get_prompt_template(self) -> str | None:
        """Return a custom prompt template, or None to use the default."""
        return None


def load_plugin(plugin_type: str) -> BasePlugin:
    """Load a plugin by platform type name (e.g. 'bilibili')."""
    import importlib

    module = importlib.import_module(f"plugin.{plugin_type}.plugin")
    class_name = f"{plugin_type.capitalize()}Plugin"
    plugin_class = getattr(module, class_name)
    return plugin_class()
