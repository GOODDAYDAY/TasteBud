"""Tests for comment analyzer — prompt building and response parsing."""

from datetime import datetime, timezone

from analyzer.comment.analyzer import CommentAnalyzer, LLMConfig
from analyzer.comment.prompts import build_analysis_prompt, format_comments_for_prompt
from core.comment import Comment, SourceInfo


def _make_comment(
        rpid: int = 1,
        content: str = "test",
        uname: str = "user",
        like: int = 0,
        video_title: str = "Test Video",
) -> Comment:
    return Comment(
        id=rpid,
        author_id=100,
        author_name=uname,
        content=content,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        likes=like,
        source=SourceInfo(title=video_title, url="https://bilibili.com/video/BV123"),
    )


class TestPromptBuilding:
    def test_format_comments(self) -> None:
        comments = [
            {"content": "好难啊", "uname": "张三", "ctime": "2026-03-01", "video_title": "教程1"},
            {"content": "学不会", "uname": "李四", "ctime": "2026-03-02", "video_title": "教程2"},
        ]
        result = format_comments_for_prompt(comments)
        assert "[0]" in result
        assert "[1]" in result
        assert "张三" in result
        assert "好难啊" in result
        assert "[视频: 教程1]" in result

    def test_build_prompt_includes_count(self) -> None:
        comments = [
            {"content": "test", "uname": "u", "ctime": "2026-03-01", "video_title": "v"},
        ]
        prompt = build_analysis_prompt(comments)
        assert "共 1 条" in prompt
        assert "痛点" in prompt
        assert "feasibility" in prompt


class TestResponseParsing:
    def _make_analyzer(self) -> CommentAnalyzer:
        return CommentAnalyzer(LLMConfig(provider="ollama", model="test"))

    def test_parse_valid_json(self) -> None:
        analyzer = self._make_analyzer()
        comments = [_make_comment(content="太难了，完全学不会")]

        raw = '''{
            "pain_points": [
                {
                    "description": "学习曲线陡峭",
                    "feasibility": "可以通过分步教程解决",
                    "feasibility_level": "high",
                    "source_comment_indices": [0]
                }
            ],
            "summary": "用户反馈学习困难"
        }'''

        result = analyzer._parse_response(raw, comments)
        assert len(result) == 1
        assert result[0].pain_description == "学习曲线陡峭"
        assert result[0].feasibility_level == "high"
        assert len(result[0].source_comments) == 1
        assert result[0].source_comments[0].content == "太难了，完全学不会"

    def test_parse_markdown_wrapped_json(self) -> None:
        analyzer = self._make_analyzer()
        comments = [_make_comment()]

        raw = '''Here is the analysis:
```json
{
    "pain_points": [
        {
            "description": "test pain",
            "feasibility": "doable",
            "feasibility_level": "medium",
            "source_comment_indices": [0]
        }
    ],
    "summary": "test summary"
}
```'''

        result = analyzer._parse_response(raw, comments)
        assert len(result) == 1
        assert result[0].feasibility_level == "medium"

    def test_parse_invalid_json_returns_empty(self) -> None:
        analyzer = self._make_analyzer()
        result = analyzer._parse_response("not json at all", [])
        assert result == []

    def test_parse_empty_pain_points(self) -> None:
        analyzer = self._make_analyzer()
        raw = '{"pain_points": [], "summary": "no issues"}'
        result = analyzer._parse_response(raw, [])
        assert result == []

    def test_out_of_range_index_ignored(self) -> None:
        analyzer = self._make_analyzer()
        comments = [_make_comment()]

        raw = '''{
            "pain_points": [
                {
                    "description": "test",
                    "feasibility": "ok",
                    "feasibility_level": "low",
                    "source_comment_indices": [0, 99]
                }
            ],
            "summary": ""
        }'''

        result = analyzer._parse_response(raw, comments)
        assert len(result[0].source_comments) == 1  # index 99 ignored

    def test_extract_summary(self) -> None:
        analyzer = self._make_analyzer()
        raw = '{"pain_points": [], "summary": "用户普遍反馈不错"}'
        summary = analyzer._extract_summary(raw)
        assert summary == "用户普遍反馈不错"


class TestSampling:
    def test_no_sampling_under_limit(self) -> None:
        analyzer = CommentAnalyzer(LLMConfig(max_comments=10))
        comments = [_make_comment(rpid=i) for i in range(5)]
        result = analyzer._sample(comments)
        assert len(result) == 5

    def test_sampling_over_limit(self) -> None:
        analyzer = CommentAnalyzer(LLMConfig(max_comments=10))
        comments = [_make_comment(rpid=i, like=i) for i in range(50)]
        result = analyzer._sample(comments)
        assert len(result) <= 10

    def test_sampling_includes_high_liked(self) -> None:
        analyzer = CommentAnalyzer(LLMConfig(max_comments=5))
        comments = [_make_comment(rpid=i, like=i * 10) for i in range(20)]
        result = analyzer._sample(comments)
        rpids = {c.id for c in result}
        # Highest liked (rpid=19, like=190) should be included
        assert 19 in rpids
