"""Pipeline configuration and run models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CollectorConfig:
    """Collector section of a pipeline config.

    Only ``type`` is generic. Everything else goes into ``plugin_config``
    and is parsed by the plugin itself via ``BasePlugin.parse_config()``.
    """

    type: str = "bilibili"
    plugin_config: dict = field(default_factory=dict)


@dataclass
class LLMConfig:
    """LLM section of analyzer config."""

    provider: str = "ollama"
    model: str = "qwen2.5:14b"
    base_url: str = "http://localhost:11434"
    api_token_env: str = ""  # Environment variable name for API token
    api_token_path: str = ""  # Path to file containing API token
    max_comments: int = 200


@dataclass
class AnalyzerConfig:
    """Analyzer section of a pipeline config."""

    window_size: int = 100
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass
class NotifierConfig:
    """A single notifier in a pipeline config."""

    type: str = "local"  # "local" (save to JSON file)
    output_dir: str = ""  # output directory for local notifier


@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""

    name: str = ""
    description: str = ""
    enabled: bool = True  # False to skip this pipeline
    interval: int = 1  # Loop interval in minutes
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)
    notifiers: list[NotifierConfig] = field(default_factory=list)


@dataclass
class PipelineRun:
    """Result of a single pipeline execution."""

    pipeline_name: str = ""
    status: str = ""  # "collected" | "analyzed" | "notified" | "error"
    new_comments: int = 0
    pain_points_found: int = 0
    notifications_sent: int = 0
    error: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
