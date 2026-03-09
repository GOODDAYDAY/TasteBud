"""Async HTTP client for Bilibili API with rate limiting and wbi signing."""

from __future__ import annotations

import asyncio
import hashlib
import struct
import time
import urllib.parse

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

# WBI mixin key reorder table (fixed, from Bilibili's JS)
_WBI_MIXIN_ORDER = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(img_key: str, sub_key: str) -> str:
    """Generate mixin key from img_key and sub_key."""
    raw = img_key + sub_key
    return "".join(raw[i] for i in _WBI_MIXIN_ORDER if i < len(raw))[:32]


def _filter_wbi_value(value: str | int) -> str:
    """Filter characters that Bilibili rejects in wbi-signed params."""
    s = str(value)
    for ch in "!'()*":
        s = s.replace(ch, "")
    return s


def _sign_wbi(params: dict[str, str | int], mixin_key: str) -> dict[str, str | int]:
    """Add wbi signature (wts + w_rid) to params."""
    params = {k: _filter_wbi_value(v) for k, v in params.items()}
    params["wts"] = str(int(time.time()))
    # Sort by key and encode
    query = urllib.parse.urlencode(sorted(params.items()))
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params


class BilibiliClient:
    """Async HTTP client for Bilibili public API."""

    def __init__(
            self,
            cookie: dict[str, str] | None = None,
            rate_limit: float = 0.3,
            retry_wait: float = 60.0,
            max_retries: int = 3,
    ) -> None:
        headers = dict(_DEFAULT_HEADERS)
        cookies = cookie or {}
        self._client = httpx.AsyncClient(
            headers=headers,
            cookies=cookies,
            timeout=30.0,
        )
        self._rate_limit = rate_limit
        self._retry_wait = retry_wait
        self._max_retries = max_retries
        self._last_request: float = 0.0
        self._mixin_key: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> BilibiliClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _get(self, url: str, params: dict[str, str | int] | None = None) -> dict:
        """Rate-limited GET request with 429 retry."""
        for attempt in range(1, self._max_retries + 1):
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request
            if elapsed < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            resp = await self._client.get(url, params=params)
            self._last_request = asyncio.get_event_loop().time()

            if resp.status_code == 429:
                print(
                    f"  [429] Rate limited, waiting {self._retry_wait:.0f}s... (attempt {attempt}/{self._max_retries})")
                await asyncio.sleep(self._retry_wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            code = data.get("code")
            if code != 0:
                msg = data.get("message", "Unknown Bilibili API error")
                print(f"  [Bilibili API] code={code}, message={msg}")
                log.warning("bilibili_api_error", code=code, message=msg, url=url)

            return data

        # All retries exhausted
        raise httpx.HTTPStatusError(
            f"429 Too Many Requests after {self._max_retries} retries",
            request=resp.request,
            response=resp,
        )

    async def _get_wbi(self, url: str, params: dict[str, str | int] | None = None) -> dict:
        """Rate-limited GET request with wbi signature."""
        mixin_key = await self._ensure_mixin_key()
        signed = _sign_wbi(params or {}, mixin_key)
        return await self._get(url, params=signed)

    async def _ensure_mixin_key(self) -> str:
        """Fetch and cache the wbi mixin key from /nav API."""
        if self._mixin_key is not None:
            return self._mixin_key

        data = await self._get("https://api.bilibili.com/x/web-interface/nav")
        wbi_img = data.get("data", {}).get("wbi_img", {})

        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        # Extract key from URL: .../xxx.png -> xxx
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0] if img_url else ""
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0] if sub_url else ""

        self._mixin_key = _get_mixin_key(img_key, sub_key)
        return self._mixin_key

    # -- Video APIs ----

    async def get_user_videos(
            self, mid: int, page: int = 1, page_size: int = 30
    ) -> dict:
        """Get a user's video list."""
        return await self._get_wbi(
            "https://api.bilibili.com/x/space/wbi/arc/search",
            params={"mid": mid, "pn": page, "ps": page_size, "order": "pubdate"},
        )

    async def get_video_info(self, bvid: str) -> dict:
        """Get video metadata by BV id."""
        return await self._get(
            "https://api.bilibili.com/x/web-interface/view",
            params={"bvid": bvid},
        )

    # -- Search APIs --

    async def search_videos(
            self,
            keyword: str,
            order: str = "pubdate",
            page: int = 1,
            page_size: int = 20,
    ) -> dict:
        """Search for videos by keyword.

        Args:
            keyword: Search query.
            order: Sort order — "pubdate" (newest), "click" (views), "scores" (relevance).
            page: Page number (1-based).
            page_size: Results per page (max 50).
        """
        return await self._get_wbi(
            "https://api.bilibili.com/x/web-interface/wbi/search/type",
            params={
                "search_type": "video",
                "keyword": keyword,
                "order": order,
                "page": page,
                "pagesize": page_size,
            },
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
