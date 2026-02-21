"""Tests for feedback + preference learning loop."""

import json
from pathlib import Path

from collector.base import TagResult
from engine.feedback import submit_feedback, load_feedback
from engine.preference import load_preferences, save_preferences


class TestPreferences:
    def test_load_empty(self, tmp_path: Path) -> None:
        assert load_preferences(tmp_path) == {}

    def test_save_and_load(self, tmp_path: Path) -> None:
        prefs = {"landscape": 2.0, "gore": -1.5}
        save_preferences(prefs, tmp_path)
        loaded = load_preferences(tmp_path)
        assert loaded == prefs

    def test_file_location(self, tmp_path: Path) -> None:
        save_preferences({"x": 1.0}, tmp_path)
        assert (tmp_path / "preferences.json").exists()


class TestFeedback:
    def test_no_feedback_returns_none(self, tmp_path: Path) -> None:
        assert load_feedback("ehentai", "123", tmp_path) is None

    def test_like_boosts_tags(self, tmp_path: Path) -> None:
        tags = [
            TagResult(name="landscape", category="general"),
            TagResult(name="sunset", category="general"),
        ]
        # Create gallery dir so feedback can be saved
        (tmp_path / "ehentai" / "123").mkdir(parents=True)

        prefs = submit_feedback("ehentai", "123", "like", tags, tmp_path)

        assert prefs["landscape"] == 0.5
        assert prefs["sunset"] == 0.5

        # feedback.json should exist
        fb = load_feedback("ehentai", "123", tmp_path)
        assert fb is not None
        assert fb["rating"] == "like"

    def test_dislike_penalizes_tags(self, tmp_path: Path) -> None:
        tags = [TagResult(name="gore", category="other")]
        (tmp_path / "ehentai" / "456").mkdir(parents=True)

        prefs = submit_feedback("ehentai", "456", "dislike", tags, tmp_path)
        assert prefs["gore"] == -0.5

    def test_cumulative_feedback(self, tmp_path: Path) -> None:
        """Multiple feedbacks accumulate weights."""
        tags = [TagResult(name="landscape")]
        (tmp_path / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / "ehentai" / "2").mkdir(parents=True)

        submit_feedback("ehentai", "1", "like", tags, tmp_path)
        prefs = submit_feedback("ehentai", "2", "like", tags, tmp_path)
        assert prefs["landscape"] == 1.0  # 0.5 + 0.5

    def test_mixed_feedback(self, tmp_path: Path) -> None:
        """Like and dislike on same tag partially cancel out."""
        tags = [TagResult(name="abstract")]
        (tmp_path / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / "ehentai" / "2").mkdir(parents=True)

        submit_feedback("ehentai", "1", "like", tags, tmp_path)
        prefs = submit_feedback("ehentai", "2", "dislike", tags, tmp_path)
        assert prefs["abstract"] == 0.0  # 0.5 - 0.5

    def test_feedback_with_existing_preferences(self, tmp_path: Path) -> None:
        """Feedback adjusts existing preference weights."""
        save_preferences({"landscape": 3.0}, tmp_path)
        tags = [TagResult(name="landscape")]
        (tmp_path / "ehentai" / "1").mkdir(parents=True)

        prefs = submit_feedback("ehentai", "1", "like", tags, tmp_path)
        assert prefs["landscape"] == 3.5
