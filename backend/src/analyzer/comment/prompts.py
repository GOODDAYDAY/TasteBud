"""LLM prompt templates for comment analysis."""

PAIN_POINT_ANALYSIS_PROMPT = """\
你是一个产品分析专家。以下是来自评论区的用户评论。

请分析这些评论，完成以下任务：
1. 识别用户遇到的所有痛点、难点和未被满足的需求
2. 对每个痛点，评估当前技术是否能够解决（可行性为 high/medium/low/uncertain）
3. 给出简要的技术可行性分析说明
4. 对每个痛点，标注支撑该判断的原始评论编号

请严格按以下 JSON 格式输出（不要输出其他内容）：
{{
  "pain_points": [
    {{
      "description": "痛点描述",
      "feasibility": "技术可行性分析说明",
      "feasibility_level": "high|medium|low|uncertain",
      "source_comment_indices": [0, 3, 7]
    }}
  ],
  "summary": "整体评论区概况（1-2句话）"
}}

如果没有发现任何痛点，返回空的 pain_points 列表。

以下是评论列表（共 {count} 条）：

{comments}
"""


def format_comments_for_prompt(
        comments: list[dict],
) -> str:
    """Format comment list for insertion into the prompt.

    Each comment dict should have: content, uname, ctime, video_title.
    """
    lines: list[str] = []
    for i, c in enumerate(comments):
        video = c.get("video_title", "")
        prefix = f"[视频: {video}] " if video else ""
        lines.append(
            f"[{i}] {prefix}{c['uname']} ({c['ctime']}): {c['content']}"
        )
    return "\n".join(lines)


def build_analysis_prompt(comments: list[dict]) -> str:
    """Build the complete analysis prompt with formatted comments."""
    formatted = format_comments_for_prompt(comments)
    return PAIN_POINT_ANALYSIS_PROMPT.format(
        count=len(comments),
        comments=formatted,
    )
