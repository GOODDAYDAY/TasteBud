"""Data models for comment analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommentContext:
    """Original comment referenced in analysis results."""

    content: str
    author_name: str
    created_at: str
    source_title: str
    source_url: str
    comment_id: int = 0


@dataclass
class PainPoint:
    """A single user pain point identified by AI."""

    pain_description: str
    feasibility: str  # technical feasibility analysis text
    feasibility_level: str  # "high" | "medium" | "low" | "uncertain"
    source_comments: list[CommentContext] = field(default_factory=list)


@dataclass
class CommentAnalysisResult:
    """Result of AI analysis on a batch of comments."""

    pipeline_name: str
    target_id: str
    target_title: str
    total_comments_analyzed: int
    pain_points: list[PainPoint] = field(default_factory=list)
    raw_summary: str = ""
    analyzed_at: datetime = field(default_factory=datetime.now)
    llm_model: str = ""
