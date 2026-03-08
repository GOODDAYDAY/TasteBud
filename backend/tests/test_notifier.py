"""Tests for notification template rendering."""

from datetime import datetime, timezone

from analyzer.comment.models import (
    CommentAnalysisResult,
    CommentContext,
    PainPoint,
)
from plugin.bilibili.template import render_analysis_text


class TestTemplateRendering:
    def _make_result(self) -> CommentAnalysisResult:
        return CommentAnalysisResult(
            pipeline_name="test_pipeline",
            target_id="BV123",
            target_title="Test Video",
            total_comments_analyzed=50,
            pain_points=[
                PainPoint(
                    pain_description="用户找不到导出功能",
                    feasibility="可以在菜单栏增加导出按钮",
                    feasibility_level="high",
                    source_comments=[
                        CommentContext(
                            content="导出在哪里啊？",
                            author_name="张三",
                            created_at="2026-03-01 12:00",
                            source_title="教程视频",
                            source_url="https://bilibili.com/video/BV123",
                            comment_id=1,
                        ),
                    ],
                ),
                PainPoint(
                    pain_description="性能太慢",
                    feasibility="需要重构底层架构",
                    feasibility_level="low",
                    source_comments=[],
                ),
            ],
            raw_summary="用户反馈了导出和性能两个问题",
            analyzed_at=datetime(2026, 3, 8, tzinfo=timezone.utc),
            llm_model="ollama/qwen2.5:14b",
        )

    def test_title_contains_pipeline_name(self) -> None:
        result = self._make_result()
        title, _ = render_analysis_text(result)
        assert "test_pipeline" in title
        assert "TasteBud" in title

    def test_body_contains_pain_points(self) -> None:
        result = self._make_result()
        _, body = render_analysis_text(result)
        assert "用户找不到导出功能" in body
        assert "性能太慢" in body
        assert "2 个用户痛点" in body

    def test_body_contains_feasibility(self) -> None:
        result = self._make_result()
        _, body = render_analysis_text(result)
        assert "high" in body
        assert "low" in body

    def test_body_contains_source_comments(self) -> None:
        result = self._make_result()
        _, body = render_analysis_text(result)
        assert "导出在哪里啊？" in body
        assert "张三" in body

    def test_body_contains_summary(self) -> None:
        result = self._make_result()
        _, body = render_analysis_text(result)
        assert "用户反馈了导出和性能两个问题" in body

    def test_empty_pain_points(self) -> None:
        result = CommentAnalysisResult(
            pipeline_name="test",
            target_id="BV123",
            target_title="Test",
            total_comments_analyzed=10,
            pain_points=[],
        )
        title, body = render_analysis_text(result)
        assert "0 个用户痛点" in body
