"""Tests for pipeline YAML config loading and CLI entry."""

from pathlib import Path

import pytest

# Only run if pyyaml is installed
yaml = pytest.importorskip("yaml")

from pipeline.config import find_pipeline_configs, load_pipeline_config
from pipeline.main import list_pipelines

SAMPLE_YAML = """\
name: test_pipeline
description: "Monitor UP主 comments"
schedule: "*/30 * * * *"

collector:
  type: bilibili
  mode: user
  target: "12345678"
  max_videos: 5
  include_replies: true
  auth:
    cookie_path: ~/.tastebud/cookie.json

analyzer:
  window_size: 100
  llm:
    provider: ollama
    model: qwen2.5:14b
    base_url: http://localhost:11434
    max_comments: 200

notifier:
  - type: local
    output_dir: ./output
"""


class TestPipelineConfig:
    def test_load_basic(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(SAMPLE_YAML, encoding="utf-8")

        config = load_pipeline_config(config_file)

        assert config.name == "test_pipeline"
        assert config.schedule == "*/30 * * * *"

    def test_collector_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(SAMPLE_YAML, encoding="utf-8")

        config = load_pipeline_config(config_file)

        assert config.collector.type == "bilibili"
        assert config.collector.mode == "user"
        assert config.collector.target == "12345678"
        assert config.collector.max_videos == 5
        assert config.collector.include_replies is True
        assert "cookie.json" in config.collector.cookie_path

    def test_analyzer_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(SAMPLE_YAML, encoding="utf-8")

        config = load_pipeline_config(config_file)

        assert config.analyzer.window_size == 100
        assert config.analyzer.llm.provider == "ollama"
        assert config.analyzer.llm.model == "qwen2.5:14b"
        assert config.analyzer.llm.max_comments == 200

    def test_notifier_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(SAMPLE_YAML, encoding="utf-8")

        config = load_pipeline_config(config_file)

        assert len(config.notifiers) == 1
        assert config.notifiers[0].type == "local"
        assert config.notifiers[0].output_dir == "./output"

    def test_enabled_defaults_true(self, tmp_path: Path) -> None:
        config_file = tmp_path / "test.yaml"
        config_file.write_text(SAMPLE_YAML, encoding="utf-8")

        config = load_pipeline_config(config_file)
        assert config.enabled is True

    def test_enabled_false(self, tmp_path: Path) -> None:
        disabled_yaml = "name: disabled_pipeline\nenabled: false\ncollector:\n  target: '123'\n"
        config_file = tmp_path / "disabled.yaml"
        config_file.write_text(disabled_yaml, encoding="utf-8")

        config = load_pipeline_config(config_file)
        assert config.enabled is False

    def test_defaults_for_missing_fields(self, tmp_path: Path) -> None:
        minimal = "name: minimal\ncollector:\n  target: '123'\n"
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(minimal, encoding="utf-8")

        config = load_pipeline_config(config_file)

        assert config.name == "minimal"
        assert config.enabled is True  # default
        assert config.collector.mode == "user"  # default
        assert config.analyzer.window_size == 100  # default
        assert config.notifiers == []


class TestFindPipelines:
    def test_find_all_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "a.yaml").write_text("name: a\ncollector:\n  target: '1'\n")
        (tmp_path / "b.yaml").write_text("name: b\ncollector:\n  target: '2'\n")
        (tmp_path / "readme.txt").write_text("not a pipeline")

        found = find_pipeline_configs(tmp_path)
        assert len(found) == 2
        assert all(p.suffix == ".yaml" for p in found)

    def test_find_empty_dir(self, tmp_path: Path) -> None:
        found = find_pipeline_configs(tmp_path)
        assert found == []

    def test_find_nonexistent_dir(self, tmp_path: Path) -> None:
        found = find_pipeline_configs(tmp_path / "nope")
        assert found == []


class TestListPipelines:
    def test_list_shows_enabled_status(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / "on.yaml").write_text(
            "name: enabled_one\nenabled: true\ncollector:\n  target: '1'\n"
        )
        (tmp_path / "off.yaml").write_text(
            "name: disabled_one\nenabled: false\ncollector:\n  target: '2'\n"
        )

        list_pipelines(tmp_path)
        output = capsys.readouterr().out

        assert "enabled_one" in output
        assert "ON" in output
        assert "disabled_one" in output
        assert "OFF" in output
