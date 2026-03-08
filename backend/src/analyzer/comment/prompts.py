"""LLM prompt templates for comment analysis."""

PAIN_POINT_ANALYSIS_PROMPT = """\
你是一个产品分析专家，也是后端开发专家。以下是来自评论区的用户评论。

请分析这些评论，完成以下任务：
1. 识别用户遇到的所有痛点、难点和未被满足的需求
2. 对每个痛点，评估当前技术是否能够解决（可行性为 high/medium/low/uncertain）。
    2.1 我希望的是，通过我和AI一起合作编写代码，来解决这个痛点，这样比较不错。比如他觉得在玩galgame的时候文本不是中文，这个痛点是可以通过编写一个工具来解决的，这个就是high的可行性。
    2.2 不能是什么大的，比如改造供应链，解决伊拉克战争这种
    2.3 "@AI全文总结 帮总结这些内容" 这种的肯定不算是需求，这里本质上是在调用其他工具解决自己问题，不是用户的痛点了。
    2.4 不要硬件需求，比如说需要更大的屏幕，更快的电脑，这些我解决不了的，这些也不算是痛点了。
    2.5 也不要用户自己的问题，比如说我太笨了，不会操作，这些也不算是痛点了。
    2.6 我要额外开发新东西，或者新插件，或者新软件来解决痛点。让我去改别人的代码，就有点不那么行，属于低优先级。
3. 给出简要的技术可行性分析说明
4. 对每个痛点，标注支撑该判断的原始评论编号

给你举个例子，如果评论区有以下评论：
[0] 用户A: 我在玩galgame的时候，那些文本不是中文，想要一个工具能帮我把galgame里的文本翻译成中文。
就算是一个痛点了，可以考虑修复

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
