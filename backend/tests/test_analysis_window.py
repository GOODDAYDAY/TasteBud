"""Tests for the comment analysis window."""

from pathlib import Path

from analyzer.comment.window import (
    add_pending,
    get_pending_count,
    reset_pending,
    should_analyze,
)


class TestAnalysisWindow:
    def test_initial_count_is_zero(self, tmp_path: Path) -> None:
        assert get_pending_count(tmp_path, "video", "BV123") == 0

    def test_add_pending(self, tmp_path: Path) -> None:
        result = add_pending(tmp_path, "video", "BV123", 50)
        assert result == 50
        assert get_pending_count(tmp_path, "video", "BV123") == 50

    def test_add_pending_accumulates(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV123", 30)
        add_pending(tmp_path, "video", "BV123", 40)
        assert get_pending_count(tmp_path, "video", "BV123") == 70

    def test_reset_pending(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV123", 100)
        reset_pending(tmp_path, "video", "BV123")
        assert get_pending_count(tmp_path, "video", "BV123") == 0

    def test_should_analyze_below_threshold(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV123", 50)
        assert should_analyze(tmp_path, "video", "BV123", threshold=100) is False

    def test_should_analyze_at_threshold(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV123", 100)
        assert should_analyze(tmp_path, "video", "BV123", threshold=100) is True

    def test_should_analyze_above_threshold(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV123", 150)
        assert should_analyze(tmp_path, "video", "BV123", threshold=100) is True

    def test_isolated_by_target(self, tmp_path: Path) -> None:
        add_pending(tmp_path, "video", "BV111", 100)
        add_pending(tmp_path, "video", "BV222", 10)
        assert should_analyze(tmp_path, "video", "BV111", threshold=50) is True
        assert should_analyze(tmp_path, "video", "BV222", threshold=50) is False
