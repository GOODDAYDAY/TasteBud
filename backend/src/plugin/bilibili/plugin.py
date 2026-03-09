"""Bilibili plugin — implements BasePlugin for the Bilibili platform."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import structlog

from analyzer.comment.models import CommentAnalysisResult
from core.comment import Comment, CommentBatch, SourceInfo
from pipeline.base import BasePlugin
from plugin.bilibili.auth import load_cookie
from plugin.bilibili.client import BilibiliClient
from plugin.bilibili.collector import BilibiliCommentCollector
from plugin.bilibili.template import render_analysis_text

log = structlog.get_logger()


class BilibiliPlugin(BasePlugin):
    """Bilibili platform plugin."""

    def __init__(self) -> None:
        # Populated by parse_config()
        self._mode: str = "user"
        self._target: str = ""
        self._max_videos: int = 0
        self._include_replies: bool = True
        self._cookie_path: Path | None = None
        self._search_order: str = "pubdate"

    def parse_config(self, plugin_config: dict) -> None:
        """Parse bilibili-specific config from YAML collector section."""
        self._mode = plugin_config.get("mode", "user")
        self._target = str(plugin_config.get("target", ""))
        self._max_videos = plugin_config.get("max_videos", 0)
        self._include_replies = plugin_config.get("include_replies", True)
        self._search_order = plugin_config.get("search_order", "pubdate")

        cookie_raw = plugin_config.get("auth", {}).get("cookie_path", "")
        self._cookie_path = Path(cookie_raw).expanduser() if cookie_raw else None

    async def ensure_auth(self) -> bool:
        """Check if Bilibili cookie exists; trigger QR login if not."""
        cookie = load_cookie(self._cookie_path)

        if cookie is not None:
            return True

        print(f"\n  No Bilibili login cookie found.")
        print("  Starting QR code login...\n")

        from plugin.bilibili.login import qr_login

        result = await qr_login(self._cookie_path)
        return result is not None

    async def collect(
            self, base_dir: Path
    ) -> AsyncIterator[CommentBatch]:
        """Collect comments from Bilibili, yielding each batch immediately."""
        cookie = load_cookie(self._cookie_path)

        async with BilibiliClient(cookie=cookie) as client:
            collector = BilibiliCommentCollector(
                client=client,
                base_dir=base_dir,
                include_replies=self._include_replies,
            )

            if self._mode == "user":
                async for batch in collector.collect_by_user(
                        int(self._target), max_videos=self._max_videos
                ):
                    yield batch
            elif self._mode == "video":
                batch = await collector.collect_by_video(self._target)
                if batch.comments:
                    yield batch
            elif self._mode == "article":
                batch = await collector.collect_by_article(int(self._target))
                if batch.comments:
                    yield batch
            elif self._mode == "search":
                async for batch in collector.collect_by_search(
                        self._target, order=self._search_order, max_videos=self._max_videos
                ):
                    yield batch
            else:
                log.warning("unknown_collector_mode", mode=self._mode)

    def save_cursor(self, batch: CommentBatch, base_dir: Path) -> None:
        """Save cursor after batch is persisted to disk."""
        if not batch.comments or not batch.cursor:
            return
        from plugin.bilibili.cursor import save_cursor
        from plugin.bilibili.models import Cursor

        cursor = Cursor(last_rpid=int(batch.cursor))
        save_cursor(base_dir, batch.target_type, batch.target_id, cursor)

    def render_notification(
            self, result: CommentAnalysisResult
    ) -> tuple[str, str]:
        """Render analysis result using the Bilibili template."""
        return render_analysis_text(result)

    def serialize_batch(self, batch: CommentBatch) -> dict:
        """Serialize a comment batch to a JSON-compatible dict."""
        return {
            "platform": batch.platform,
            "target_type": batch.target_type,
            "target_id": batch.target_id,
            "target_title": batch.target_title,
            "fetched_at": batch.fetched_at.isoformat(),
            "cursor": batch.cursor,
            "comments": [
                {
                    "id": c.id,
                    "author_id": c.author_id,
                    "author_name": c.author_name,
                    "content": c.content,
                    "created_at": c.created_at.isoformat(),
                    "likes": c.likes,
                    "reply_count": c.reply_count,
                    "parent_id": c.parent_id,
                }
                for c in batch.comments
            ],
        }

    def deserialize_comments(self, data: dict) -> list[Comment]:
        """Deserialize comments from a stored batch dict."""
        source = SourceInfo(
            title=data.get("target_title", ""),
            url=f"https://www.bilibili.com/video/{data.get('target_id', '')}",
        )

        comments: list[Comment] = []
        for c in data.get("comments", []):
            comments.append(
                Comment(
                    id=str(c["id"]),
                    author_id=str(c["author_id"]),
                    author_name=c["author_name"],
                    content=c["content"],
                    created_at=datetime.fromisoformat(c["created_at"]),
                    likes=c.get("likes", 0),
                    reply_count=c.get("reply_count", 0),
                    parent_id=str(c["parent_id"]) if c.get("parent_id") is not None else None,
                    source=SourceInfo(
                        title=c.get("source_title", source.title),
                        url=c.get("source_url", source.url),
                    ),
                )
            )
        return comments
