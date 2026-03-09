"""Pipeline YAML configuration loader."""

from __future__ import annotations

from pathlib import Path

import structlog

from pipeline.models import (
    AnalyzerConfig,
    CollectorConfig,
    LLMConfig,
    NotifierConfig,
    PipelineConfig,
)

log = structlog.get_logger()

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


def load_pipeline_config(path: Path) -> PipelineConfig:
    """Load a pipeline config from a YAML file."""
    if not _HAS_YAML:
        msg = "pyyaml is required for pipeline configs: pip install pyyaml"
        raise ImportError(msg)

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    # Collector — only extract 'type'; everything else is plugin-specific
    c = raw.get("collector", {})
    plugin_config = {k: v for k, v in c.items() if k != "type"}
    collector = CollectorConfig(
        type=c.get("type", "bilibili"),
        plugin_config=plugin_config,
    )

    # Analyzer
    a = raw.get("analyzer", {})
    llm_raw = a.get("llm", {})
    llm = LLMConfig(
        provider=llm_raw.get("provider", "ollama"),
        model=llm_raw.get("model", "qwen2.5:14b"),
        base_url=llm_raw.get("base_url", "http://localhost:11434"),
        api_token_env=llm_raw.get("api_token_env", ""),
        api_token_path=llm_raw.get("api_token_path", ""),
        max_comments=llm_raw.get("max_comments", 200),
    )
    analyzer = AnalyzerConfig(
        window_size=a.get("window_size", 100),
        llm=llm,
    )

    # Notifiers
    notifiers: list[NotifierConfig] = []
    for n in raw.get("notifier", raw.get("notifiers", [])):
        notifiers.append(
            NotifierConfig(
                type=n.get("type", "local"),
                output_dir=n.get("output_dir", ""),
            )
        )

    return PipelineConfig(
        name=raw.get("name", path.stem),
        description=raw.get("description", ""),
        enabled=raw.get("enabled", True),
        interval=raw.get("interval", 1),
        collector=collector,
        analyzer=analyzer,
        notifiers=notifiers,
    )


def find_pipeline_configs(pipelines_dir: Path) -> list[Path]:
    """Find all .yaml pipeline config files in a directory."""
    if not pipelines_dir.exists():
        return []
    return sorted(pipelines_dir.glob("*.yaml"))
