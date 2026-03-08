"""Tests for the source tag analyzer."""

import pytest

from analyzer.source_tag.analyzer import SourceTagAnalyzer
from collector.base import RawContent, TagResult


class TestSourceTagAnalyzer:
    @pytest.fixture
    def analyzer(self) -> SourceTagAnalyzer:
        return SourceTagAnalyzer()

    async def test_normalizes_tags(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(
            source="test", source_id="1",
            tags=[TagResult(name="  Blue Sky  ", category="general")],
        )
        result = await analyzer.analyze(raw)
        assert result.enriched_tags[0].name == "blue_sky"

    async def test_empty_tags(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(source="test", source_id="2")
        result = await analyzer.analyze(raw)
        assert result.enriched_tags == []
        assert result.theme == []

    async def test_extracts_themes_from_parody_and_character(
        self, analyzer: SourceTagAnalyzer
    ) -> None:
        raw = RawContent(
            source="test_source", source_id="3",
            tags=[
                TagResult(name="fate grand order", category="parody"),
                TagResult(name="saber", category="character"),
                TagResult(name="fantasy", category="general"),
            ],
        )
        result = await analyzer.analyze(raw)
        assert "fate_grand_order" in result.theme
        assert "saber" in result.theme
        # "general" category tags are NOT themes
        assert "fantasy" not in result.theme

    async def test_extracts_warnings(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(
            source="test", source_id="4",
            tags=[TagResult(name="gore", category="other")],
        )
        result = await analyzer.analyze(raw)
        assert "gore" in result.content_warnings

    async def test_quality_from_rating(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(
            source="test_source", source_id="5",
            metadata={"rating": "4.5"},
        )
        result = await analyzer.analyze(raw)
        assert result.quality == 0.9  # 4.5 / 5.0

    async def test_audience_from_category(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(
            source="test_source", source_id="6",
            metadata={"category": "manga"},
        )
        result = await analyzer.analyze(raw)
        assert result.target_audience == "general"

    async def test_extracts_style(self, analyzer: SourceTagAnalyzer) -> None:
        raw = RawContent(
            source="test", source_id="7",
            tags=[
                TagResult(name="full color", category="other"),
                TagResult(name="sketch", category="other"),
            ],
        )
        result = await analyzer.analyze(raw)
        # Takes first matching style tag
        assert result.style in ("full_color", "sketch")
