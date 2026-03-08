"""Bilibili-specific notification template rendering."""

from __future__ import annotations

from analyzer.comment.models import CommentAnalysisResult


def render_analysis_text(result: CommentAnalysisResult) -> tuple[str, str]:
    """Render analysis result into (title, body) for notification.

    Returns plain text / Markdown body suitable for WeChat or email.
    """
    title = f"[TasteBud] {result.pipeline_name} 评论分析报告"

    lines: list[str] = []
    lines.append(f"分析了 {result.total_comments_analyzed} 条评论")
    lines.append(f"发现 {len(result.pain_points)} 个用户痛点")
    lines.append(f"模型: {result.llm_model}")
    lines.append("")

    if result.raw_summary:
        lines.append(f"**概况**: {result.raw_summary}")
        lines.append("")

    for i, pp in enumerate(result.pain_points, 1):
        level_emoji = {
            "high": "🟢",
            "medium": "🟡",
            "low": "🔴",
            "uncertain": "⚪",
        }.get(pp.feasibility_level, "⚪")

        lines.append("---")
        lines.append(f"**痛点 {i}**: {pp.pain_description}")
        lines.append(f"可行性: {level_emoji} {pp.feasibility_level} — {pp.feasibility}")
        lines.append("")

        if pp.source_comments:
            lines.append("相关评论:")
            for sc in pp.source_comments[:5]:  # Max 5 comments per pain point
                source_ref = f"[{sc.source_title}]" if sc.source_title else ""
                lines.append(
                    f"  - {source_ref} {sc.author_name} ({sc.created_at}): \"{sc.content}\""
                )
            if len(pp.source_comments) > 5:
                lines.append(f"  - ...还有 {len(pp.source_comments) - 5} 条相关评论")
        lines.append("")

    body = "\n".join(lines)
    return title, body
