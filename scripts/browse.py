"""Browse e-hentai galleries and download selected ones.

Usage:
    python scripts/browse.py              # browse front page
    python scripts/browse.py "search terms"  # search

Output structure:
    downloads/ehentai/{gid}/
        images/       ← image files
        tags.txt      ← human-readable tags
        data.json     ← raw metadata
"""

import asyncio
import io
import re
import sys
import time
from pathlib import Path

import httpx

# Fix Windows console encoding for CJK characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend/src to path so collector imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from collector.base import RawContent, TagResult
from collector.ehentai.collector import EHentaiCollector
from collector.storage import images_dir, save_metadata

_COLLECTOR = EHentaiCollector()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

_BASE_URL = "https://e-hentai.org"
_API_URL = "https://api.e-hentai.org/api.php"

# Extract gallery links from listing page
_GALLERY_LINK_RE = re.compile(
    r'href="https://e-hentai\.org/g/(\d+)/([a-f0-9]+)/"'
)

# For download
_IMAGE_PAGE_RE = re.compile(r'href="(https://e-hentai\.org/s/[a-f0-9]+/\d+-\d+)"')
_IMAGE_SRC_RE = re.compile(r'<img\s+id="img"\s+src="([^"]+)"')
_TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+images")

# E-Hentai tag namespaces
_TAG_CATEGORIES: dict[str, str] = {
    "artist": "artist", "group": "group", "parody": "parody",
    "character": "character", "female": "female", "male": "male",
    "mixed": "mixed", "language": "language", "reclass": "reclass", "other": "other",
}

DELAY = 1.0


# ── Browse ──────────────────────────────────────────────────────────

async def fetch_listing(
    client: httpx.AsyncClient, page: int = 0, search: str = ""
) -> list[dict[str, str]]:
    """Fetch one listing page, then use API to get titles and categories."""
    params: dict[str, str | int] = {"page": page}
    if search:
        params["f_search"] = search

    resp = await client.get(_BASE_URL, params=params, follow_redirects=True)
    resp.raise_for_status()

    # Extract (gid, token) pairs, deduplicate
    seen: set[str] = set()
    gid_list: list[tuple[str, str]] = []
    for gid, token in _GALLERY_LINK_RE.findall(resp.text):
        if gid not in seen:
            seen.add(gid)
            gid_list.append((gid, token))

    if not gid_list:
        return []

    # Use API to get metadata
    payload = {
        "method": "gdata",
        "gidlist": [[int(gid), token] for gid, token in gid_list],
        "namespace": 1,
    }
    api_resp = await client.post(_API_URL, json=payload, timeout=30.0)
    api_resp.raise_for_status()
    metadata = {str(g["gid"]): g for g in api_resp.json().get("gmetadata", [])}

    galleries: list[dict[str, str]] = []
    for gid, token in gid_list:
        m = metadata.get(gid, {})
        galleries.append({
            "url": f"{_BASE_URL}/g/{gid}/{token}/",
            "gid": gid,
            "token": token,
            "title": m.get("title_jpn") or m.get("title", "?"),
            "category": m.get("category", "?"),
            "rating": m.get("rating", "?"),
            "filecount": m.get("filecount", "?"),
            # Store raw API data for metadata saving
            "_api_data": m,
        })

    return galleries


def show_galleries(galleries: list[dict[str, str]], page: int) -> None:
    print(f"\n{'=' * 80}")
    print(f"  Page {page}  ({len(galleries)} galleries)")
    print(f"{'=' * 80}")
    for i, g in enumerate(galleries):
        cat = g["category"][:10].ljust(10)
        pages = g.get("filecount", "?").rjust(4)
        rating = g.get("rating", "?")
        print(f"  [{i+1:2d}] {cat}  {pages}p  ★{rating}  {g['title']}")
    print(f"{'=' * 80}")
    print("  Commands: number to download, n=next, p=prev, s=search, q=quit")


def _build_raw_content(gallery: dict) -> RawContent:
    """Convert a gallery dict (with _api_data) to RawContent for storage."""
    api = gallery.get("_api_data", {})

    # Parse tags
    tags: list[TagResult] = []
    for tag_str in api.get("tags", []):
        if ":" in tag_str:
            namespace, name = tag_str.split(":", 1)
            category = _TAG_CATEGORIES.get(namespace, namespace)
        else:
            name = tag_str
            category = "other"
        tags.append(TagResult(name=name, category=category))

    return RawContent(
        source="ehentai",
        source_id=gallery["gid"],
        title=gallery["title"],
        url=gallery["url"],
        thumbnail_url=api.get("thumb", ""),
        tags=tags,
        metadata={
            "category": api.get("category", ""),
            "rating": api.get("rating", "0"),
            "filecount": api.get("filecount", "0"),
            "uploader": api.get("uploader", ""),
            "title_english": api.get("title", ""),
            "title_japanese": api.get("title_jpn", ""),
            "posted": api.get("posted", ""),
        },
    )


# ── Download ────────────────────────────────────────────────────────

async def download_gallery(client: httpx.AsyncClient, gallery: dict) -> None:
    """Download a gallery with structured storage."""
    # Save metadata first
    content = _build_raw_content(gallery)
    gdir = save_metadata(content, _COLLECTOR.category)
    img_dir = images_dir(_COLLECTOR.category, content.source, content.source_id)

    print(f"\n  Downloading to {gdir}")
    print(f"  Tags: {len(content.tags)}, saved data.json + tags.txt")

    gallery_url = gallery["url"]

    # Get total pages
    resp = await client.get(gallery_url, follow_redirects=True)
    resp.raise_for_status()
    html = resp.text

    total_match = _TOTAL_RE.search(html)
    total_images = int(total_match.group(1).replace(",", "")) if total_match else 0

    first_page_links = _IMAGE_PAGE_RE.findall(html)
    per_page = len(first_page_links) if first_page_links else 20
    total_gallery_pages = (total_images + per_page - 1) // per_page if per_page else 1

    print(f"  {total_images} images, {total_gallery_pages} gallery pages")

    # Collect all image page URLs
    image_page_urls: list[str] = []
    seen: set[str] = set()
    for link in first_page_links:
        if link not in seen:
            seen.add(link)
            image_page_urls.append(link)

    for p in range(1, total_gallery_pages):
        print(f"  Scanning page {p+1}/{total_gallery_pages} ...", end="\r")
        resp = await client.get(f"{gallery_url}?p={p}", follow_redirects=True)
        resp.raise_for_status()
        for link in _IMAGE_PAGE_RE.findall(resp.text):
            if link not in seen:
                seen.add(link)
                image_page_urls.append(link)
        await asyncio.sleep(DELAY)

    print(f"  Found {len(image_page_urls)} images, downloading ...        ")

    # Download each
    downloaded = 0
    skipped = 0
    start = time.time()

    for i, page_url in enumerate(image_page_urls):
        num_match = re.search(r"-(\d+)$", page_url)
        num = num_match.group(1) if num_match else str(i + 1)

        if list(img_dir.glob(f"{num.zfill(4)}.*")):
            skipped += 1
            continue

        try:
            resp = await client.get(page_url, follow_redirects=True)
            resp.raise_for_status()
            m = _IMAGE_SRC_RE.search(resp.text)
            if not m:
                continue

            img_url = m.group(1)
            ext = "jpg"
            for e in ("webp", "png", "gif"):
                if f".{e}" in img_url:
                    ext = e
                    break

            dest = img_dir / f"{num.zfill(4)}.{ext}"
            img_resp = await client.get(img_url, follow_redirects=True)
            img_resp.raise_for_status()
            dest.write_bytes(img_resp.content)
            downloaded += 1

            elapsed = time.time() - start
            print(
                f"  [{i+1}/{len(image_page_urls)}] {dest.name}  "
                f"({downloaded} ok, {elapsed:.0f}s)",
                end="\r",
            )
        except httpx.HTTPError as e:
            print(f"  [{i+1}] FAILED: {e}                        ")

        await asyncio.sleep(DELAY)

    print(f"\n  Done! downloaded={downloaded} skipped={skipped}")


# ── Main loop ───────────────────────────────────────────────────────

async def main() -> None:
    search = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    page = 0

    async with httpx.AsyncClient(headers=_HEADERS, timeout=60.0) as client:
        while True:
            galleries = await fetch_listing(client, page=page, search=search)
            if not galleries:
                print("No galleries found.")
                page = max(0, page - 1)
                continue

            show_galleries(galleries, page)

            cmd = input("\n> ").strip().lower()
            if cmd == "q":
                break
            elif cmd == "n":
                page += 1
            elif cmd == "p":
                page = max(0, page - 1)
            elif cmd == "s":
                search = input("Search: ").strip()
                page = 0
            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(galleries):
                    g = galleries[idx]
                    print(f"\n  Selected: {g['title']}")
                    await download_gallery(client, g)
                else:
                    print("  Invalid number")
            else:
                print("  Unknown command")


if __name__ == "__main__":
    asyncio.run(main())
