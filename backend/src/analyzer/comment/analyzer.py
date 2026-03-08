"""Comment analyzer — batch AI analysis for user pain point discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import structlog

from analyzer.comment.models import (
    CommentAnalysisResult,
    CommentContext,
    PainPoint,
)
from analyzer.comment.prompts import build_analysis_prompt
from core.comment import Comment

log = structlog.get_logger()


@dataclass
class LLMConfig:
    """Configuration for the LLM provider."""

    provider: str = "ollama"  # "ollama" | "openai" | "anthropic"
    model: str = "qwen2.5:14b"
    api_token: str = ""
    base_url: str = "http://localhost:11434"
    max_comments: int = 200  # max comments per analysis batch


class CommentAnalyzer:
    """Batch-analyze comments to discover user pain points."""

    def __init__(self, llm_config: LLMConfig) -> None:
        self._config = llm_config

    async def analyze(
            self,
            comments: list[Comment],
            pipeline_name: str = "",
            target_id: str = "",
            target_title: str = "",
    ) -> CommentAnalysisResult:
        """Analyze a batch of comments for pain points."""
        # Sample if too many
        sampled = self._sample(comments)

        # Build prompt
        comment_dicts = [
            {
                "content": c.content,
                "uname": c.author_name,
                "ctime": c.created_at.strftime("%Y-%m-%d %H:%M"),
                "video_title": c.source.title,
            }
            for c in sampled
        ]
        prompt = build_analysis_prompt(comment_dicts)

        # Call LLM
        raw_response = await self._call_llm(prompt)

        # Parse response
        pain_points = self._parse_response(raw_response, sampled)

        return CommentAnalysisResult(
            pipeline_name=pipeline_name,
            target_id=target_id,
            target_title=target_title,
            total_comments_analyzed=len(sampled),
            pain_points=pain_points,
            raw_summary=self._extract_summary(raw_response),
            analyzed_at=datetime.now(timezone.utc),
            llm_model=f"{self._config.provider}/{self._config.model}",
        )

    def _sample(self, comments: list[Comment]) -> list[Comment]:
        """Sample comments if exceeding max_comments limit.

        Strategy: top-N by likes + most recent + random fill.
        """
        max_n = self._config.max_comments
        if len(comments) <= max_n:
            return comments

        # Top by likes
        by_likes = sorted(comments, key=lambda c: c.likes, reverse=True)
        top_liked = by_likes[: max_n // 3]

        # Most recent
        by_time = sorted(comments, key=lambda c: c.created_at, reverse=True)
        recent = by_time[: max_n // 3]

        # Merge and fill with remaining
        seen_ids = {c.id for c in top_liked} | {c.id for c in recent}
        remaining = [c for c in comments if c.id not in seen_ids]

        fill_count = max_n - len(seen_ids)
        result = list(top_liked) + [c for c in recent if c.id not in {x.id for x in top_liked}]
        result.extend(remaining[:fill_count])

        return result[:max_n]

    async def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM provider."""
        if self._config.provider == "ollama":
            return await self._call_ollama(prompt)
        if self._config.provider in ("openai", "anthropic"):
            return await self._call_openai_compatible(prompt)
        msg = f"Unknown LLM provider: {self._config.provider}"
        raise ValueError(msg)

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama API."""
        url = f"{self._config.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "")

    async def _call_openai_compatible(self, prompt: str) -> str:
        """Call OpenAI-compatible API (works for OpenAI, Anthropic proxy, etc.)."""
        url = f"{self._config.base_url.rstrip('/')}/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self._config.api_token}"}
        payload = {
            "model": self._config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def _parse_response(
            self, raw: str, comments: list[Comment]
    ) -> list[PainPoint]:
        """Parse LLM JSON response into PainPoint list."""
        try:
            # Extract JSON from response (may be wrapped in markdown)
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
        except (json.JSONDecodeError, IndexError):
            log.warning("llm_response_parse_failed", raw=raw[:200])
            return []

        pain_points: list[PainPoint] = []
        for pp in data.get("pain_points", []):
            # Map comment indices to CommentContext
            indices = pp.get("source_comment_indices", [])
            source_comments = []
            for idx in indices:
                if 0 <= idx < len(comments):
                    c = comments[idx]
                    source_comments.append(
                        CommentContext(
                            content=c.content,
                            author_name=c.author_name,
                            created_at=c.created_at.strftime("%Y-%m-%d %H:%M"),
                            source_title=c.source.title,
                            source_url=c.source.url,
                            comment_id=c.id,
                        )
                    )

            pain_points.append(
                PainPoint(
                    pain_description=pp.get("description", ""),
                    feasibility=pp.get("feasibility", ""),
                    feasibility_level=pp.get("feasibility_level", "uncertain"),
                    source_comments=source_comments,
                )
            )

        return pain_points

    @staticmethod
    def _extract_summary(raw: str) -> str:
        """Extract the summary field from LLM response."""
        try:
            json_str = raw
            if "```json" in raw:
                json_str = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                json_str = raw.split("```")[1].split("```")[0]
            data = json.loads(json_str.strip())
            return data.get("summary", "")
        except (json.JSONDecodeError, IndexError):
            return ""
