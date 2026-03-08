"""Bilibili comment collector — incremental collection from videos, articles, users."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import structlog

from core.comment import Comment, CommentBatch, SourceInfo
from plugin.bilibili.client import (
    COMMENT_TYPE_ARTICLE,
    COMMENT_TYPE_VIDEO,
    BilibiliClient,
)
from plugin.bilibili.cursor import load_cursor, save_cursor
from plugin.bilibili.models import Cursor, VideoInfo

log = structlog.get_logger()


class BilibiliCommentCollector:
    """Collect comments from Bilibili with incremental cursor support."""

    def __init__(
            self,
            client: BilibiliClient,
            base_dir: Path,
            include_replies: bool = True,
            max_pages: int = 50,
    ) -> None:
        self._client = client
        self._base_dir = base_dir
        self._include_replies = include_replies
        self._max_pages = max_pages

    async def collect_by_video(self, bvid: str) -> CommentBatch:
        """Collect comments from a single video (incremental)."""
        # Get avid from API (local BV→AV algorithm is unreliable for newer videos)
        video_info = await self._fetch_video_info(bvid)
        avid = video_info.avid

        # Load cursor
        cursor = load_cursor(self._base_dir, "video", bvid)

        # Collect new comments
        comments = await self._collect_comments(
            oid=avid,
            type_=COMMENT_TYPE_VIDEO,
            cursor=cursor,
            video=video_info,
        )

        # Update cursor
        if comments:
            cursor.last_rpid = max(c.id for c in comments)
            save_cursor(self._base_dir, "video", bvid, cursor)

        log.info(
            "bilibili_video_collected",
            bvid=bvid,
            new_comments=len(comments),
            last_rpid=cursor.last_rpid,
        )

        return CommentBatch(
            platform="bilibili",
            target_type="video",
            target_id=bvid,
            target_title=video_info.title,
            comments=comments,
            fetched_at=datetime.now(timezone.utc),
            cursor=str(cursor.last_rpid),
        )

    async def collect_by_user(
            self, mid: int, max_videos: int = 10
    ) -> list[CommentBatch]:
        """Collect comments from a user's recent videos."""
        resp = await self._client.get_user_videos(mid, page=1, page_size=max_videos)

        vlist = (
            resp.get("data", {}).get("list", {}).get("vlist", [])
        )
        if not vlist:
            log.warning("bilibili_no_videos", mid=mid)
            return []

        batches: list[CommentBatch] = []
        for v in vlist[:max_videos]:
            bvid = v.get("bvid", "")
            if not bvid:
                continue
            batch = await self.collect_by_video(bvid)
            if batch.comments:
                batches.append(batch)

        log.info(
            "bilibili_user_collected",
            mid=mid,
            videos=len(vlist[:max_videos]),
            batches_with_new=len(batches),
        )
        return batches

    async def collect_by_article(self, cvid: int) -> CommentBatch:
        """Collect comments from a single article (incremental)."""
        target_id = f"cv{cvid}"
        cursor = load_cursor(self._base_dir, "article", target_id)

        video = VideoInfo(
            url=f"https://www.bilibili.com/read/cv{cvid}",
        )

        comments = await self._collect_comments(
            oid=cvid,
            type_=COMMENT_TYPE_ARTICLE,
            cursor=cursor,
            video=video,
        )

        if comments:
            cursor.last_rpid = max(c.id for c in comments)
            save_cursor(self._base_dir, "article", target_id, cursor)

        return CommentBatch(
            platform="bilibili",
            target_type="article",
            target_id=target_id,
            target_title=f"Article cv{cvid}",
            comments=comments,
            fetched_at=datetime.now(timezone.utc),
            cursor=str(cursor.last_rpid),
        )

    # -- Internal helpers --

    async def _fetch_video_info(self, bvid: str) -> VideoInfo:
        """Fetch video metadata and AV ID from API."""
        try:
            resp = await self._client.get_video_info(bvid)
            data = resp.get("data", {})
            owner = data.get("owner", {})
            return VideoInfo(
                bvid=bvid,
                avid=data.get("aid", 0),
                title=data.get("title", ""),
                url=f"https://www.bilibili.com/video/{bvid}",
                up_mid=owner.get("mid", 0),
                up_name=owner.get("name", ""),
            )
        except Exception:
            log.warning("bilibili_video_info_failed", bvid=bvid)
            # Fallback to local conversion
            return VideoInfo(bvid=bvid, avid=BilibiliClient.bv_to_av(bvid))

    async def _collect_comments(
            self,
            oid: int,
            type_: int,
            cursor: Cursor,
            video: VideoInfo,
    ) -> list[Comment]:
        """Collect comments incrementally, stopping at cursor.last_rpid."""
        all_comments: list[Comment] = []
        stop = False

        for page in range(1, self._max_pages + 1):
            resp = await self._client.get_comments(
                oid=oid, type_=type_, sort=0, pn=page
            )

            replies = resp.get("data", {}).get("replies") or []
            if not replies:
                break

            for reply in replies:
                rpid = reply.get("rpid", 0)

                # Stop if we've seen this comment before
                if rpid <= cursor.last_rpid:
                    stop = True
                    break

                comment = self._parse_comment(reply, video)
                all_comments.append(comment)

                # Collect sub-replies
                if self._include_replies and reply.get("rcount", 0) > 0:
                    sub_comments = await self._collect_sub_replies(
                        oid, rpid, type_, video
                    )
                    all_comments.extend(sub_comments)

            if stop:
                break

        return all_comments

    async def _collect_sub_replies(
            self,
            oid: int,
            root_rpid: int,
            type_: int,
            video: VideoInfo,
    ) -> list[Comment]:
        """Collect replies to a specific comment."""
        sub_comments: list[Comment] = []

        for page in range(1, 11):  # Max 10 pages of sub-replies
            resp = await self._client.get_comment_replies(
                oid=oid, rpid=root_rpid, type_=type_, pn=page
            )
            replies = resp.get("data", {}).get("replies") or []
            if not replies:
                break

            for reply in replies:
                comment = self._parse_comment(reply, video, parent_rpid=root_rpid)
                sub_comments.append(comment)

        return sub_comments

    @staticmethod
    def _parse_comment(
            reply: dict, video: VideoInfo, parent_rpid: int | None = None
    ) -> Comment:
        """Parse a single API reply dict into a generic Comment."""
        member = reply.get("member", {})
        content = reply.get("content", {})

        return Comment(
            id=reply.get("rpid", 0),
            author_id=member.get("mid", 0),
            author_name=member.get("uname", ""),
            content=content.get("message", ""),
            created_at=datetime.fromtimestamp(
                reply.get("ctime", 0), tz=timezone.utc
            ),
            likes=reply.get("like", 0),
            reply_count=reply.get("rcount", 0),
            parent_id=parent_rpid,
            source=SourceInfo(
                title=video.title,
                url=video.url,
            ),
        )
