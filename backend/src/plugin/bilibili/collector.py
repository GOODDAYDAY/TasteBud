"""Bilibili comment collector — incremental collection from videos, articles, users."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path

import structlog

from core.comment import Comment, CommentBatch, SourceInfo
from plugin.bilibili.client import (
    COMMENT_TYPE_ARTICLE,
    COMMENT_TYPE_VIDEO,
    BilibiliClient,
)
from plugin.bilibili.cursor import load_cursor
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
        # Get avid from API (local BV->AV algorithm is unreliable for newer videos)
        video_info = await self._fetch_video_info(bvid)
        avid = video_info.avid
        title = video_info.title or bvid
        print(f"    [{bvid}] {title}")

        # Load cursor
        cursor = load_cursor(self._base_dir, "video", bvid)

        # Collect new comments
        comments = await self._collect_comments(
            oid=avid,
            type_=COMMENT_TYPE_VIDEO,
            cursor=cursor,
            video=video_info,
        )

        if comments:
            print(f"      +{len(comments)} new comments")
        else:
            print(f"      (no new comments)")

        # cursor value is passed in the batch; runner persists it after saving the batch
        new_cursor = str(max(c.id for c in comments)) if comments else str(cursor.last_rpid)

        return CommentBatch(
            platform="bilibili",
            target_type="video",
            target_id=bvid,
            target_title=video_info.title,
            comments=comments,
            fetched_at=datetime.now(timezone.utc),
            cursor=new_cursor,
        )

    async def collect_by_user(
            self, mid: int, max_videos: int = 10
    ) -> AsyncIterator[CommentBatch]:
        """Collect comments from a user's recent videos, yielding each batch."""
        print(f"  Fetching video list for user {mid}...")
        resp = await self._client.get_user_videos(mid, page=1, page_size=max_videos)

        vlist = (
            resp.get("data", {}).get("list", {}).get("vlist", [])
        )
        if not vlist:
            print(f"  No videos found for user {mid}")
            return

        videos = vlist[:max_videos]
        print(f"  Found {len(videos)} video(s), collecting comments...")
        for v in videos:
            bvid = v.get("bvid", "")
            if not bvid:
                continue
            try:
                batch = await self.collect_by_video(bvid)
                if batch.comments:
                    yield batch
            except Exception as e:
                print(f"      ERROR collecting {bvid}: {e}")

    async def collect_by_search(
            self, keyword: str, order: str = "pubdate", max_videos: int = 20
    ) -> AsyncIterator[CommentBatch]:
        """Search for videos by keyword and collect comments from each."""
        print(f"  Searching for \"{keyword}\" (order={order})...")
        resp = await self._client.search_videos(keyword, order=order)
        results = resp.get("data", {}).get("result", [])

        if not results:
            print(f"  No search results for \"{keyword}\"")
            return

        videos = results[:max_videos]
        print(f"  Found {len(results)} result(s), checking top {len(videos)}...")
        for item in videos:
            bvid = item.get("bvid", "")
            if not bvid:
                continue
            try:
                batch = await self.collect_by_video(bvid)
                if batch.comments:
                    yield batch
            except Exception as e:
                print(f"      ERROR collecting {bvid}: {e}")

    async def collect_by_article(self, cvid: int) -> CommentBatch:
        """Collect comments from a single article (incremental)."""
        target_id = f"cv{cvid}"
        print(f"    [cv{cvid}] Collecting article comments...")
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
            print(f"      +{len(comments)} new comments")
        else:
            print(f"      (no new comments)")

        new_cursor = str(max(c.id for c in comments)) if comments else str(cursor.last_rpid)

        return CommentBatch(
            platform="bilibili",
            target_type="article",
            target_id=target_id,
            target_title=f"Article cv{cvid}",
            comments=comments,
            fetched_at=datetime.now(timezone.utc),
            cursor=new_cursor,
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
        except Exception as e:
            print(f"    [{bvid}] Failed to fetch video info: {e}")
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
                if len(comment.content) > 10:
                    all_comments.append(comment)

                # Collect sub-replies
                if self._include_replies and reply.get("rcount", 0) > 0:
                    sub_comments = await self._collect_sub_replies(
                        oid, rpid, type_, video
                    )
                    all_comments.extend(
                        c for c in sub_comments if len(c.content) > 10
                    )

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
