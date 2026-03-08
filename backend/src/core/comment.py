"""Generic comment data models — platform-agnostic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceInfo:
    """Metadata about the source a comment belongs to (video, article, etc.)."""

    title: str = ""
    url: str = ""


@dataclass
class Comment:
    """A single platform-agnostic comment."""

    id: int
    author_id: int
    author_name: str
    content: str
    created_at: datetime
    likes: int = 0
    reply_count: int = 0
    parent_id: int | None = None
    source: SourceInfo = field(default_factory=SourceInfo)


@dataclass
class CommentBatch:
    """A batch of comments collected from a single target."""

    platform: str = ""
    target_type: str = ""  # "video" | "article" | "dynamic"
    target_id: str = ""
    target_title: str = ""
    comments: list[Comment] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.now)
    cursor: str = ""
