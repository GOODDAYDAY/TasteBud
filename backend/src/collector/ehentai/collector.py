"""E-Hentai gallery collector.

Flow:
1. Fetch listing page HTML → extract gallery IDs + tokens
2. Call E-Hentai API (gdata) → get structured metadata
3. Return RawContent with tags already parsed by namespace
"""

import re

import httpx
import structlog

from collector.base import BaseCollector, RawContent, TagResult
from core.exceptions import CollectorError

logger = structlog.get_logger()

_GALLERY_PATTERN = re.compile(r"https://e-hentai\.org/g/(\d+)/([a-f0-9]+)/")

_API_URL = "https://api.e-hentai.org/api.php"
_BASE_URL = "https://e-hentai.org"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# E-Hentai tag namespaces → our category names
_TAG_CATEGORIES: dict[str, str] = {
    "artist": "artist",
    "group": "group",
    "parody": "parody",
    "character": "character",
    "female": "female",
    "male": "male",
    "mixed": "mixed",
    "language": "language",
    "reclass": "reclass",
    "other": "other",
}


class EHentaiCollector(BaseCollector):
    """Collects gallery metadata from e-hentai.org."""

    async def collect(self, **kwargs: str | int) -> list[RawContent]:
        """Fetch galleries from e-hentai listing page, then get metadata via API.

        Kwargs:
            page: Page number (0-indexed). Default 0.
            search: Search query string. Default empty.
        """
        page = int(kwargs.get("page", 0))
        search = str(kwargs.get("search", ""))

        # Step 1: fetch listing page to get gallery IDs
        galleries = await self._fetch_listing(page=page, search=search)
        if not galleries:
            logger.info("ehentai_no_galleries", page=page, search=search)
            return []

        # Step 2: get metadata via API (max 25 per request)
        metadata = await self._fetch_metadata(galleries)

        # Step 3: convert to RawContent
        results: list[RawContent] = []
        for gdata in metadata:
            raw = RawContent(
                source="ehentai",
                source_id=str(gdata["gid"]),
                title=gdata.get("title_jpn") or gdata.get("title", ""),
                url=f"{_BASE_URL}/g/{gdata['gid']}/{gdata['token']}/",
                thumbnail_url=gdata.get("thumb", ""),
                metadata={
                    "category": gdata.get("category", ""),
                    "rating": gdata.get("rating", "0"),
                    "filecount": gdata.get("filecount", "0"),
                    "uploader": gdata.get("uploader", ""),
                },
            )
            raw.tags = self.parse_tags(raw, tags=gdata.get("tags", []))
            results.append(raw)

        logger.info("ehentai_collected", count=len(results), page=page, search=search)
        return results

    def parse_tags(self, raw: RawContent, **kwargs: object) -> list[TagResult]:
        """Parse e-hentai tags which are formatted as 'namespace:tagname'."""
        tag_strings = kwargs.get("tags", [])
        if not isinstance(tag_strings, list):
            return []

        tags: list[TagResult] = []
        for tag_str in tag_strings:
            if not isinstance(tag_str, str):
                continue
            if ":" in tag_str:
                namespace, name = tag_str.split(":", 1)
                category = _TAG_CATEGORIES.get(namespace, namespace)
            else:
                name = tag_str
                category = "other"
            tags.append(TagResult(name=name, category=category))

        return tags

    async def _fetch_listing(
        self, *, page: int = 0, search: str = ""
    ) -> list[tuple[int, str]]:
        """Fetch gallery listing page and extract (gid, token) pairs."""
        params: dict[str, str | int] = {"page": page}
        if search:
            params["f_search"] = search

        try:
            async with httpx.AsyncClient(headers=_HEADERS) as client:
                resp = await client.get(_BASE_URL, params=params, timeout=30.0)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as e:
            raise CollectorError(f"E-Hentai listing request failed: {e}") from e

        matches = _GALLERY_PATTERN.findall(html)
        # Deduplicate while preserving order
        seen: set[str] = set()
        galleries: list[tuple[int, str]] = []
        for gid_str, token in matches:
            if gid_str not in seen:
                seen.add(gid_str)
                galleries.append((int(gid_str), token))

        logger.debug("ehentai_listing_parsed", gallery_count=len(galleries), page=page)
        return galleries

    async def _fetch_metadata(
        self, galleries: list[tuple[int, str]]
    ) -> list[dict[str, object]]:
        """Fetch gallery metadata via E-Hentai API (gdata method)."""
        payload = {
            "method": "gdata",
            "gidlist": [[gid, token] for gid, token in galleries],
            "namespace": 1,
        }

        try:
            async with httpx.AsyncClient(headers=_HEADERS) as client:
                resp = await client.post(_API_URL, json=payload, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            raise CollectorError(f"E-Hentai API request failed: {e}") from e

        return data.get("gmetadata", [])  # type: ignore[no-any-return]
