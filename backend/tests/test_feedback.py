"""Tests for feedback + preference learning loop."""

from pathlib import Path

from collector.base import TagResult
from engine.feedback import (
    load_feedback,
    load_feedback_log,
    replay,
    submit_feedback,
)
from engine.preference import load_preferences, save_preferences


CAT = "manga"


class TestPreferences:
    def test_load_empty(self, tmp_path: Path) -> None:
        assert load_preferences(CAT, tmp_path) == {}

    def test_save_and_load(self, tmp_path: Path) -> None:
        prefs = {"landscape": 2.0, "gore": -1.5}
        save_preferences(CAT, prefs, tmp_path)
        loaded = load_preferences(CAT, tmp_path)
        assert loaded == prefs

    def test_categories_are_isolated(self, tmp_path: Path) -> None:
        save_preferences("manga", {"art": 1.0}, tmp_path)
        save_preferences("news", {"politics": 2.0}, tmp_path)
        assert load_preferences("manga", tmp_path) == {"art": 1.0}
        assert load_preferences("news", tmp_path) == {"politics": 2.0}


class TestFeedback:
    def test_no_feedback_returns_none(self, tmp_path: Path) -> None:
        assert load_feedback(CAT, "ehentai", "123", tmp_path) is None

    def test_like_boosts_tags(self, tmp_path: Path) -> None:
        tags = [
            TagResult(name="landscape", category="general"),
            TagResult(name="sunset", category="general"),
        ]
        (tmp_path / CAT / "ehentai" / "123").mkdir(parents=True)

        prefs = submit_feedback(CAT, "ehentai", "123", "like", tags, tmp_path)
        assert prefs["landscape"] == 0.5
        assert prefs["sunset"] == 0.5

        fb = load_feedback(CAT, "ehentai", "123", tmp_path)
        assert fb is not None
        assert fb["rating"] == "like"

    def test_dislike_penalizes_tags(self, tmp_path: Path) -> None:
        tags = [TagResult(name="gore", category="other")]
        (tmp_path / CAT / "ehentai" / "456").mkdir(parents=True)

        prefs = submit_feedback(CAT, "ehentai", "456", "dislike", tags, tmp_path)
        assert prefs["gore"] == -0.5

    def test_cumulative_feedback(self, tmp_path: Path) -> None:
        tags = [TagResult(name="landscape")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / CAT / "ehentai" / "2").mkdir(parents=True)

        submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)
        prefs = submit_feedback(CAT, "ehentai", "2", "like", tags, tmp_path)
        assert prefs["landscape"] == 1.0

    def test_feedback_with_existing_preferences(self, tmp_path: Path) -> None:
        save_preferences(CAT, {"landscape": 3.0}, tmp_path)
        tags = [TagResult(name="landscape")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)

        prefs = submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)
        assert prefs["landscape"] == 3.5


class TestFeedbackLog:
    def test_log_created_on_submit(self, tmp_path: Path) -> None:
        tags = [TagResult(name="landscape", category="general")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)

        submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)

        log = load_feedback_log(CAT, tmp_path)
        assert len(log) == 1
        assert log[0]["source"] == "ehentai"
        assert log[0]["rating"] == "like"
        assert log[0]["tags"] == ["landscape"]

    def test_log_appends(self, tmp_path: Path) -> None:
        tags = [TagResult(name="a")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / CAT / "ehentai" / "2").mkdir(parents=True)

        submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)
        submit_feedback(CAT, "ehentai", "2", "dislike", tags, tmp_path)

        log = load_feedback_log(CAT, tmp_path)
        assert len(log) == 2

    def test_logs_isolated_by_category(self, tmp_path: Path) -> None:
        tags = [TagResult(name="x")]
        (tmp_path / "manga" / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / "news" / "rss" / "1").mkdir(parents=True)

        submit_feedback("manga", "ehentai", "1", "like", tags, tmp_path)
        submit_feedback("news", "rss", "1", "dislike", tags, tmp_path)

        assert len(load_feedback_log("manga", tmp_path)) == 1
        assert len(load_feedback_log("news", tmp_path)) == 1


class TestReplay:
    def test_replay_regenerates_preferences(self, tmp_path: Path) -> None:
        tags = [TagResult(name="landscape"), TagResult(name="sky")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / CAT / "ehentai" / "2").mkdir(parents=True)

        submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)
        submit_feedback(CAT, "ehentai", "2", "like", tags, tmp_path)

        prefs = replay(CAT, tmp_path, learn_rate=1.0)
        assert prefs["landscape"] == 2.0
        assert prefs["sky"] == 2.0

    def test_replay_handles_mixed_feedback(self, tmp_path: Path) -> None:
        tags = [TagResult(name="x")]
        (tmp_path / CAT / "ehentai" / "1").mkdir(parents=True)
        (tmp_path / CAT / "ehentai" / "2").mkdir(parents=True)

        submit_feedback(CAT, "ehentai", "1", "like", tags, tmp_path)
        submit_feedback(CAT, "ehentai", "2", "dislike", tags, tmp_path)

        prefs = replay(CAT, tmp_path, learn_rate=0.5)
        assert prefs["x"] == 0.0

    def test_replay_empty_log(self, tmp_path: Path) -> None:
        prefs = replay(CAT, tmp_path)
        assert prefs == {}
