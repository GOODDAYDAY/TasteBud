"""Download all images from an e-hentai gallery with structured storage.

Usage:
    python scripts/download_gallery.py https://e-hentai.org/g/3800836/e4164d7229/

Output structure:
    downloads/ehentai/{gid}/
        images/       ← image files
        tags.txt      ← human-readable tags
        data.json     ← raw metadata
"""

import asyncio
import re
import sys
import time
from pathlib import Path

import httpx

# Add backend/src to path so collector imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from collector.base import RawContent, TagResult
from collector.storage import images_dir, save_metadata

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

_API_URL = "https://api.e-hentai.org/api.php"

# Gallery page: extract image page links like /s/hash/gid-N
_IMAGE_PAGE_RE = re.compile(r'href="(https://e-hentai\.org/s/[a-f0-9]+/\d+-\d+)"')

# Image page: extract the actual image src from <img id="img">
_IMAGE_SRC_RE = re.compile(r'<img\s+id="img"\s+src="([^"]+)"')

# Gallery URL pattern
_GALLERY_URL_RE = re.compile(r"https://e-hentai\.org/g/(\d+)/([a-f0-9]+)/")

# Total image count from "Showing 1 - 20 of 1,067 images" or similar
_TOTAL_RE = re.compile(r"of\s+([\d,]+)\s+images")

# E-Hentai tag namespaces
_TAG_CATEGORIES: dict[str, str] = {
    "artist": "artist", "group": "group", "parody": "parody",
    "character": "character", "female": "female", "male": "male",
    "mixed": "mixed", "language": "language", "reclass": "reclass", "other": "other",
}

DELAY = 1.0


async def fetch_gallery_metadata(
    client: httpx.AsyncClient, gid: int, token: str
) -> RawContent | None:
    """Fetch gallery metadata via API and return as RawContent."""
    payload = {
        "method": "gdata",
        "gidlist": [[gid, token]],
        "namespace": 1,
    }
    resp = await client.post(_API_URL, json=payload, timeout=30.0)
    resp.raise_for_status()
    gmetadata = resp.json().get("gmetadata", [])
    if not gmetadata:
        return None

    g = gmetadata[0]

    # Parse tags
    tags: list[TagResult] = []
    for tag_str in g.get("tags", []):
        if ":" in tag_str:
            namespace, name = tag_str.split(":", 1)
            category = _TAG_CATEGORIES.get(namespace, namespace)
        else:
            name = tag_str
            category = "other"
        tags.append(TagResult(name=name, category=category))

    return RawContent(
        source="ehentai",
        source_id=str(g["gid"]),
        title=g.get("title_jpn") or g.get("title", ""),
        url=f"https://e-hentai.org/g/{g['gid']}/{g['token']}/",
        thumbnail_url=g.get("thumb", ""),
        tags=tags,
        metadata={
            "category": g.get("category", ""),
            "rating": g.get("rating", "0"),
            "filecount": g.get("filecount", "0"),
            "uploader": g.get("uploader", ""),
            "title_english": g.get("title", ""),
            "title_japanese": g.get("title_jpn", ""),
            "posted": g.get("posted", ""),
        },
    )


async def download_images(
    client: httpx.AsyncClient, gallery_url: str, img_dir: Path
) -> tuple[int, int, int]:
    """Download all images from a gallery into img_dir.

    Returns (downloaded, skipped, failed).
    """
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
    failed = 0
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
                failed += 1
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
            failed += 1

        await asyncio.sleep(DELAY)

    return downloaded, skipped, failed


async def main(gallery_url: str) -> None:
    m = _GALLERY_URL_RE.match(gallery_url.rstrip("/") + "/")
    if not m:
        print(f"Invalid gallery URL: {gallery_url}")
        sys.exit(1)

    gid = int(m.group(1))
    token = m.group(2)

    async with httpx.AsyncClient(headers=_HEADERS, timeout=60.0) as client:
        # Step 1: Fetch metadata via API and save data.json + tags.txt
        print("[1/3] Fetching metadata ...")
        content = await fetch_gallery_metadata(client, gid, token)
        if not content:
            print("  Failed to fetch gallery metadata.")
            sys.exit(1)

        gdir = save_metadata(content)
        print(f"  Title: {content.title}")
        print(f"  Tags: {len(content.tags)}")
        print(f"  Saved data.json + tags.txt to {gdir}\n")

        # Step 2: Download images
        print("[2/3] Downloading images ...")
        img_dir = images_dir(content.source, content.source_id)
        downloaded, skipped, failed = await download_images(
            client, gallery_url, img_dir
        )

        print(f"\n\n[3/3] Done! downloaded={downloaded} skipped={skipped} failed={failed}")
        print(f"  Saved to: {gdir}")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        url = sys.argv[1]
    else:
        url = input("Gallery URL: ").strip()

    if not url:
        print("No URL provided.")
        sys.exit(1)

    asyncio.run(main(url))
