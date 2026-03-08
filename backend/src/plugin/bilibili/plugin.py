"""Bilibili plugin — implements BasePlugin for the Bilibili platform."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog

from analyzer.comment.models import CommentAnalysisResult
from core.comment import Comment, CommentBatch, SourceInfo
from pipeline.base import BasePlugin
from pipeline.models import PipelineConfig
from plugin.bilibili.auth import load_cookie
from plugin.bilibili.client import BilibiliClient
from plugin.bilibili.collector import BilibiliCommentCollector
from plugin.bilibili.template import render_analysis_text

log = structlog.get_logger()


class BilibiliPlugin(BasePlugin):
    """Bilibili platform plugin."""

    async def ensure_auth(self, config: PipelineConfig) -> bool:
        """Check if Bilibili cookie exists; trigger QR login if not."""
        cc = config.collector
        cookie_path = Path(cc.cookie_path) if cc.cookie_path else None
        cookie = load_cookie(cookie_path)

        if cookie is not None:
            return True

        print(f"\n  [{config.name}] No Bilibili login cookie found.")
        print("  Starting QR code login...\n")

        from plugin.bilibili.login import qr_login

        result = await qr_login(cookie_path)
        return result is not None

    async def collect(
            self, config: PipelineConfig, base_dir: Path
    ) -> list[CommentBatch]:
        """Collect comments from Bilibili."""
        cc = config.collector
        cookie_path = Path(cc.cookie_path) if cc.cookie_path else None
        cookie = load_cookie(cookie_path)

        async with BilibiliClient(cookie=cookie) as client:
            collector = BilibiliCommentCollector(
                client=client,
                base_dir=base_dir,
                include_replies=cc.include_replies,
            )

            if cc.mode == "user":
                return await collector.collect_by_user(
                    int(cc.target), max_videos=cc.max_videos
                )
            if cc.mode == "video":
                batch = await collector.collect_by_video(cc.target)
                return [batch] if batch.comments else []
            if cc.mode == "article":
                batch = await collector.collect_by_article(int(cc.target))
                return [batch] if batch.comments else []

            log.warning("unknown_collector_mode", mode=cc.mode)
            return []

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
        # Source info is stored once at batch level, not per comment
        source = SourceInfo(
            title=data.get("target_title", ""),
            url=f"https://www.bilibili.com/video/{data.get('target_id', '')}",
        )

        comments: list[Comment] = []
        for c in data.get("comments", []):
            comments.append(
                Comment(
                    id=c["id"],
                    author_id=c["author_id"],
                    author_name=c["author_name"],
                    content=c["content"],
                    created_at=datetime.fromisoformat(c["created_at"]),
                    likes=c.get("likes", 0),
                    reply_count=c.get("reply_count", 0),
                    parent_id=c.get("parent_id"),
                    # Backwards compat: old files may still have per-comment source
                    source=SourceInfo(
                        title=c.get("source_title", source.title),
                        url=c.get("source_url", source.url),
                    ),
                )
            )
        return comments
