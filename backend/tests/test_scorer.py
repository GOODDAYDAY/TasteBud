"""Tests for the tag scoring engine."""

from collector.base import TagResult
from engine.scorer import TagScorer


class TestTagScorer:
    def setup_method(self) -> None:
        self.scorer = TagScorer()

    def test_empty_tags_returns_zero(self) -> None:
        score, matched = self.scorer.score({}, [])
        assert score == 0.0
        assert matched == []

    def test_empty_preferences_returns_zero(self) -> None:
        tags = [TagResult(name="landscape", category="general")]
        score, matched = self.scorer.score({}, tags)
        assert score == 0.0
        assert matched == []

    def test_no_matching_tags(self) -> None:
        prefs = {"portrait": 2.0}
        tags = [TagResult(name="landscape", category="general")]
        score, matched = self.scorer.score(prefs, tags)
        assert score == 0.0
        assert matched == []

    def test_positive_preference(self) -> None:
        prefs = {"landscape": 2.0}
        tags = [TagResult(name="landscape", category="general", confidence=1.0)]
        score, matched = self.scorer.score(prefs, tags)
        assert score == 2.0
        assert matched == ["landscape"]

    def test_negative_preference(self) -> None:
        prefs = {"gore": -3.0}
        tags = [TagResult(name="gore", category="other", confidence=1.0)]
        score, matched = self.scorer.score(prefs, tags)
        assert score == -3.0
        assert matched == ["gore"]

    def test_multiple_tags(self) -> None:
        prefs = {"landscape": 2.0, "sky": 1.5}
        tags = [
            TagResult(name="landscape", confidence=1.0),
            TagResult(name="sky", confidence=0.8),
            TagResult(name="tree", confidence=1.0),  # not in prefs, ignored
        ]
        score, matched = self.scorer.score(prefs, tags)
        # 2.0*1.0 + 1.5*0.8 = 2.0 + 1.2 = 3.2
        assert score == 3.2
        assert set(matched) == {"landscape", "sky"}

    def test_confidence_scales_score(self) -> None:
        prefs = {"landscape": 2.0}
        tags = [TagResult(name="landscape", confidence=0.5)]
        score, _ = self.scorer.score(prefs, tags)
        assert score == 1.0  # 2.0 * 0.5
