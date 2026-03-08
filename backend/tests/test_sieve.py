"""Tests for the three-layer sieve pipeline."""

import json
from pathlib import Path

import pytest

from collector.base import RawContent, TagResult
from engine.sieve import (
    LayerResult,
    SieveResult,
    _normalize_tag_score,
    load_sieve,
    record_layer3,
    run_layer1,
    run_layer2,
    save_sieve,
)


class TestLayerResult:
    def test_defaults(self) -> None:
        r = LayerResult(passed=True, score=0.75, threshold=0.5)
        assert r.passed is True
        assert r.score == 0.75
        assert r.threshold == 0.5
        assert r.timestamp  # auto-generated
        assert r.details == {}

    def test_custom_details(self) -> None:
        r = LayerResult(
            passed=False, score=0.2, threshold=0.5,
            details={"tag_score": 0.3, "clip_score": 0.1},
        )
        assert r.details["tag_score"] == 0.3
        assert r.details["clip_score"] == 0.1


class TestSieveResult:
    def test_empty(self) -> None:
        s = SieveResult()
        assert s.layer1 is None
        assert s.layer2 is None
        assert s.layer3 is None

    def test_to_dict(self) -> None:
        s = SieveResult(
            layer1=LayerResult(passed=True, score=0.8, threshold=0.5, timestamp="t1"),
        )
        d = s.to_dict()
        assert "layer1" in d
        assert d["layer1"]["passed"] is True
        assert d["layer1"]["score"] == 0.8
        assert "layer2" not in d
        assert "layer3" not in d

    def test_roundtrip(self) -> None:
        original = SieveResult(
            layer1=LayerResult(
                passed=True, score=0.82, threshold=0.5,
                timestamp="2026-01-01T00:00:00Z",
                details={"tag_score": 0.9, "clip_score": 0.74},
            ),
            layer2=LayerResult(
                passed=True, score=0.68, threshold=0.3,
                timestamp="2026-01-01T00:01:00Z",
                details={"model": "moondream2"},
            ),
            layer3=LayerResult(
                passed=True, score=1.0, threshold=0.0,
                timestamp="2026-01-01T00:02:00Z",
                details={"rating": "like"},
            ),
        )
        d = original.to_dict()
        restored = SieveResult.from_dict(d)
        assert restored.layer1 is not None
        assert restored.layer1.passed is True
        assert restored.layer1.score == 0.82
        assert restored.layer1.details["tag_score"] == 0.9
        assert restored.layer2 is not None
        assert restored.layer2.details["model"] == "moondream2"
        assert restored.layer3 is not None
        assert restored.layer3.details["rating"] == "like"


class TestSievePersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        sieve = SieveResult(
            layer1=LayerResult(passed=True, score=0.75, threshold=0.5, timestamp="t1"),
        )
        save_sieve("manga", "test_source", "123", sieve, base_dir=tmp_path)
        loaded = load_sieve("manga", "test_source", "123", base_dir=tmp_path)

        assert loaded is not None
        assert loaded.layer1 is not None
        assert loaded.layer1.passed is True
        assert loaded.layer1.score == 0.75

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        loaded = load_sieve("manga", "test_source", "999", base_dir=tmp_path)
        assert loaded is None

    def test_overwrite(self, tmp_path: Path) -> None:
        sieve1 = SieveResult(
            layer1=LayerResult(passed=True, score=0.5, threshold=0.3, timestamp="t1"),
        )
        save_sieve("manga", "test_source", "123", sieve1, base_dir=tmp_path)

        # Add layer2
        sieve2 = SieveResult(
            layer1=LayerResult(passed=True, score=0.5, threshold=0.3, timestamp="t1"),
            layer2=LayerResult(passed=False, score=0.1, threshold=0.3, timestamp="t2"),
        )
        save_sieve("manga", "test_source", "123", sieve2, base_dir=tmp_path)

        loaded = load_sieve("manga", "test_source", "123", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.layer1 is not None
        assert loaded.layer2 is not None
        assert loaded.layer2.passed is False

    def test_sieve_json_structure(self, tmp_path: Path) -> None:
        """Verify the on-disk JSON matches the spec."""
        sieve = SieveResult(
            layer1=LayerResult(
                passed=True, score=0.82, threshold=0.5,
                timestamp="2026-02-21T14:30:00Z",
                details={"tag_score": 0.90, "clip_score": 0.74},
            ),
        )
        path = save_sieve("manga", "test_source", "123", sieve, base_dir=tmp_path)

        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["layer1"]["passed"] is True
        assert raw["layer1"]["score"] == 0.82
        assert raw["layer1"]["threshold"] == 0.5
        assert raw["layer1"]["details"]["tag_score"] == 0.90


class TestNormalizeTagScore:
    def test_zero_gives_half(self) -> None:
        assert _normalize_tag_score(0.0) == 0.5

    def test_positive_above_half(self) -> None:
        assert _normalize_tag_score(2.0) > 0.5

    def test_negative_below_half(self) -> None:
        assert _normalize_tag_score(-2.0) < 0.5

    def test_bounded_0_to_1(self) -> None:
        assert 0.0 <= _normalize_tag_score(-100.0) < 0.5
        assert 0.5 < _normalize_tag_score(100.0) <= 1.0


class TestRunLayer1:
    @pytest.fixture()
    def content(self) -> RawContent:
        return RawContent(
            source="test_source",
            source_id="123",
            title="Test Gallery",
            tags=[
                TagResult(name="landscape", confidence=1.0),
                TagResult(name="sky", confidence=0.8),
            ],
        )

    async def test_tag_only_scoring(self, content: RawContent) -> None:
        """Layer 1 works without CLIP — pure tag scoring."""
        prefs = {"landscape": 2.0, "sky": 1.0}
        result = await run_layer1(content, prefs, threshold=0.3)
        assert result.score > 0.5  # positive prefs => above sigmoid midpoint
        assert result.passed is True
        assert result.details["matched_tags"] == ["landscape", "sky"]

    async def test_no_preferences_is_neutral(self, content: RawContent) -> None:
        """No preferences => score = 0.5 (sigmoid of 0)."""
        result = await run_layer1(content, {}, threshold=0.3)
        assert result.score == 0.5
        assert result.passed is True  # 0.5 >= 0.3

    async def test_negative_preferences_low_score(self, content: RawContent) -> None:
        """Negative prefs => score below 0.5."""
        prefs = {"landscape": -3.0, "sky": -2.0}
        result = await run_layer1(content, prefs, threshold=0.5)
        assert result.score < 0.5
        assert result.passed is False

    async def test_high_threshold_filters(self, content: RawContent) -> None:
        """High threshold can filter out even positive items."""
        prefs = {"landscape": 0.5}  # slight positive
        result = await run_layer1(content, prefs, threshold=0.9)
        assert result.passed is False

    async def test_clip_baseline_none_falls_back(self, content: RawContent) -> None:
        """When clip_baseline is None, falls back to tag-only."""
        prefs = {"landscape": 2.0}
        result = await run_layer1(content, prefs, threshold=0.3, clip_baseline=None)
        assert "clip_score" not in result.details


class TestRecordLayer3:
    def test_like(self) -> None:
        r = record_layer3("like")
        assert r.passed is True
        assert r.score == 1.0
        assert r.details["rating"] == "like"

    def test_dislike(self) -> None:
        r = record_layer3("dislike")
        assert r.passed is False
        assert r.score == 0.0
        assert r.details["rating"] == "dislike"


class TestRunLayer2:
    async def test_no_images_graceful_skip(self, tmp_path: Path) -> None:
        """Layer 2 gracefully handles missing Ollama."""
        content = RawContent(source="test_source", source_id="123", title="Test")
        empty_dir = tmp_path / "images"
        empty_dir.mkdir()
        result = await run_layer2(content, empty_dir, threshold=0.2)
        # Should not crash — returns skip result
        assert result is not None
