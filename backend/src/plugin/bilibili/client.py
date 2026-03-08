"""Async HTTP client for Bilibili API with rate limiting."""

from __future__ import annotations

import asyncio
import struct

import httpx
import structlog

log = structlog.get_logger()

# BV to AV conversion table (public algorithm)
_BV_TABLE = "fZodR9XQDSUm21yCkr6zBqiveYah8bt4xsWpHnJE7jL5VG3guMTKNPAwcF"
_BV_TR = {c: i for i, c in enumerate(_BV_TABLE)}
_BV_S = [11, 10, 3, 8, 4, 6]
_BV_XOR = 177451812
_BV_ADD = 8728348608

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

# Bilibili API comment type codes
COMMENT_TYPE_VIDEO = 1
COMMENT_TYPE_ARTICLE = 12
COMMENT_TYPE_DYNAMIC = 17


class BilibiliClient:
    """Async HTTP client for Bilibili public API."""

    def __init__(
            self,
            cookie: dict[str, str] | None = None,
            rate_limit: float = 1.0,
    ) -> None:
        headers = dict(_DEFAULT_HEADERS)
        cookies = cookie or {}
        self._client = httpx.AsyncClient(
            headers=headers,
            cookies=cookies,
            timeout=30.0,
        )
        self._rate_limit = rate_limit
        self._last_request: float = 0.0

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> BilibiliClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _get(self, url: str, params: dict[str, str | int] | None = None) -> dict:
        """Rate-limited GET request."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)

        resp = await self._client.get(url, params=params)
        self._last_request = asyncio.get_event_loop().time()
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            msg = data.get("message", "Unknown Bilibili API error")
            log.warning("bilibili_api_error", code=data.get("code"), message=msg, url=url)

        return data

    # -- Video APIs ----

    async def get_user_videos(
            self, mid: int, page: int = 1, page_size: int = 30
    ) -> dict:
        """Get a user's video list."""
        return await self._get(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            params={"mid": mid, "pn": page, "ps": page_size, "order": "pubdate"},
        )

    async def get_video_info(self, bvid: str) -> dict:
        """Get video metadata by BV id."""
        return await self._get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )

    # -- Comment APIs --

    async def get_comments(
            self,
            oid: int,
            type_: int = COMMENT_TYPE_VIDEO,
            sort: int = 0,
            pn: int = 1,
            ps: int = 20,
    ) -> dict:
        """Get comment list for a resource.

        Args:
            oid: Resource ID (AV number for videos).
            type_: Resource type (1=video, 12=article, 17=dynamic).
            sort: Sort order (0=time, 2=hot).
            pn: Page number (1-based).
            ps: Page size (max 20).
        """
        return await self._get(
            "https://api.bilibili.com/x/v2/reply",
            params={"oid": oid, "type": type_, "sort": sort, "pn": pn, "ps": ps},
        )

    async def get_comment_replies(
            self,
            oid: int,
            rpid: int,
            type_: int = COMMENT_TYPE_VIDEO,
            pn: int = 1,
            ps: int = 20,
    ) -> dict:
        """Get replies to a specific comment."""
        return await self._get(
            "https://api.bilibili.com/x/v2/reply/reply",
            params={"oid": oid, "root": rpid, "type": type_, "pn": pn, "ps": ps},
        )

    # -- BV/AV conversion --

    @staticmethod
    def bv_to_av(bvid: str) -> int:
        """Convert BV id to AV id using the public algorithm."""
        r = 0
        for i in range(6):
            r += _BV_TR[bvid[_BV_S[i]]] * (58 ** i)
        result = (r - _BV_ADD) ^ _BV_XOR
        # Handle unsigned 32-bit
        return struct.unpack("I", struct.pack("i", result))[0] if result < 0 else result
