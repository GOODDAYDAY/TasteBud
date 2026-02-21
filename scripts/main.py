"""TasteBud: interactive async entry point.

Runs the full loop: download → analyze → score → rate → learn.
Background download doesn't block the interactive menu.

Usage:
    python scripts/main.py                  # interactive mode (manga)
    python scripts/main.py --category news  # different category
"""

import asyncio
import io
import re
import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for CJK characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend/src and scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector.base import TagResult
from collector.storage import (
    category_dir,
    find_downloaded,
    find_unanalyzed,
    images_dir,
    load_analysis,
    load_item,
    save_analysis,
    save_download_result,
    save_metadata,
)
from engine.feedback import load_feedback, replay, submit_feedback
from engine.preference import load_preferences
from engine.scorer import TagScorer

DEFAULT_CATEGORY = "manga"

# Source registry: name → (url_regex, url_builder)
# url_regex extracts (gid, token) from a full URL
# url_builder(gid, token) → gallery URL
_SOURCES: dict[str, tuple[re.Pattern[str], str]] = {
    "ehentai": (
        re.compile(r"https?://e-hentai\.org/g/(\d+)/([a-f0-9]+)/?"),
        "https://e-hentai.org/g/{gid}/{token}/",
    ),
}

# For matching user input like "3796701/c3305f85d4"
_ID_TOKEN_RE = re.compile(r"^(\d+)/([a-f0-9]+)/?$")


def _parse_gallery_input(raw: str) -> tuple[str, int, str] | None:
    """Parse user input into (source, gid, token).

    Accepts:
        3796701/c3305f85d4
        https://e-hentai.org/g/3796701/c3305f85d4/

    Returns None if not recognized.
    """
    raw = raw.strip()

    # Try full URL first
    for source_name, (url_re, _) in _SOURCES.items():
        m = url_re.match(raw)
        if m:
            return source_name, int(m.group(1)), m.group(2)

    # Try bare id/token
    m = _ID_TOKEN_RE.match(raw)
    if m:
        return None, int(m.group(1)), m.group(2)  # source TBD

    return None


def _build_gallery_url(source: str, gid: int, token: str) -> str:
    _, url_template = _SOURCES[source]
    return url_template.format(gid=gid, token=token)


def _log_path(category: str) -> Path:
    """Category-level download log file."""
    return category_dir(category) / "download.log"


def _log(category: str, msg: str) -> None:
    """Append a timestamped line to the download log."""
    path = _log_path(category)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


# ── Background tasks ─────────────────────────────────────────────────

async def download_task(category: str, source: str, gid: int, token: str) -> None:
    """Download a gallery (metadata + images) in background, logging to file."""
    from download_gallery import (
        _HEADERS,
        download_images,
        fetch_gallery_metadata,
    )
    import httpx

    log = lambda msg: _log(category, msg)
    gallery_url = _build_gallery_url(source, gid, token)
    log(f"Start: {source} {gid}/{token}")

    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=60.0) as client:
            # Step 1: metadata
            content = await fetch_gallery_metadata(client, gid, token)
            if not content:
                log(f"FAILED: could not fetch metadata for {gid}")
                return

            log(f"Title: {content.title}")
            log(f"Tags: {len(content.tags)}")
            save_metadata(content, category)

            # Step 2: download all images (progress goes to log file)
            img_dir = images_dir(category, content.source, content.source_id)
            log("Downloading images ...")
            downloaded, skipped, failed = await download_images(
                client, gallery_url, img_dir, log=log,
            )

            # Step 3: mark complete
            save_download_result(
                category, content.source, content.source_id,
                downloaded, skipped, failed,
            )
            log(f"Done: {downloaded} downloaded, {skipped} skipped, {failed} failed")

            # Step 4: auto-analyze
            await analyze_new(category)

    except Exception as e:
        log(f"ERROR: {e}")


async def analyze_new(category: str) -> None:
    """Analyze items that have data.json but no analysis.json yet."""
    unanalyzed = find_unanalyzed(category)
    if not unanalyzed:
        return

    from analyzer.source_tag.analyzer import SourceTagAnalyzer

    analyzer = SourceTagAnalyzer()
    for item_path in unanalyzed:
        content = load_item(item_path)
        if not content:
            continue

        images_path = item_path / "images"
        analysis = await analyzer.analyze(
            content, images_path if images_path.exists() else None
        )
        save_analysis(category, content.source, content.source_id, analysis)

    _log(category, f"Analyzed {len(unanalyzed)} new items")


# ── Foreground commands ──────────────────────────────────────────────

def cmd_browse(category: str) -> None:
    """Browse scored items — only shows fully downloaded items."""
    scorer = TagScorer()
    prefs = load_preferences(category)
    items = find_downloaded(category)

    if not items:
        print(f"\n  No downloaded items in {category}.")
        return

    results: list[tuple[float, str, str, str, list[str]]] = []

    for idir in items:
        content = load_item(idir)
        if not content:
            continue

        # Prefer analyzed tags from disk, fall back to raw source tags
        analysis = load_analysis(category, content.source, content.source_id)
        if analysis:
            tags = [
                TagResult(
                    name=t["name"],
                    category=t.get("category", "general"),
                    confidence=t.get("confidence", 1.0),
                )
                for t in analysis.get("enriched_tags", [])
            ]
        else:
            tags = content.tags

        score, matched = scorer.score(prefs, tags)
        results.append((score, content.source, content.source_id, content.title, matched))

    results.sort(key=lambda x: x[0], reverse=True)

    print(f"\n  Category: {category}  |  {len(results)} items  |  {len(prefs)} pref tags")
    print(f"  {'Score':>7}  {'Source':>8}  {'ID':>10}  {'Match':>5}  Title")
    print(f"  {'-' * 78}")
    for score, source, sid, title, matched in results:
        title_short = title[:42] + "..." if len(title) > 42 else title
        print(f"  {score:>7.2f}  {source:>8}  {sid:>10}  {len(matched):>5}  {title_short}")


async def cmd_rate(category: str) -> None:
    """Rate unrated downloaded items. Non-blocking input."""
    items = find_downloaded(category)
    if not items:
        print(f"\n  No downloaded items in {category}.")
        return

    # Filter to unrated
    unrated = []
    for item_path in items:
        source, sid = item_path.parent.name, item_path.name
        if load_feedback(category, source, sid) is None:
            unrated.append(item_path)

    print(f"\n  {len(items)} items, {len(unrated)} unrated")

    if not unrated:
        print("  All items rated!")
        return

    for item_path in unrated:
        content = load_item(item_path)
        if not content:
            continue

        source, sid = item_path.parent.name, item_path.name
        print(f"\n  --- {source}/{sid} ---")
        print(f"  {content.title}")
        if content.url:
            print(f"  {content.url}")
        tag_names = [t.name for t in content.tags[:12]]
        if tag_names:
            extra = f" (+{len(content.tags) - 12})" if len(content.tags) > 12 else ""
            print(f"  Tags: {', '.join(tag_names)}{extra}")

        print("  [l]ike  [d]islike  [s]kip  [q]uit rating")
        cmd = (await asyncio.to_thread(input, "  > ")).strip().lower()

        if cmd in ("l", "like"):
            submit_feedback(category, source, sid, "like", content.tags)
            print("  -> liked")
        elif cmd in ("d", "dislike"):
            submit_feedback(category, source, sid, "dislike", content.tags)
            # Delete images to free disk space
            img_path = item_path / "images"
            if img_path.is_dir():
                import shutil
                shutil.rmtree(img_path)
            print("  -> disliked (images deleted)")
        elif cmd == "q":
            break
        else:
            print("  -> skipped")

    prefs = load_preferences(category)
    print(f"\n  Preferences now have {len(prefs)} tags.")


def cmd_prefs(category: str) -> None:
    """Show current preferences sorted by weight."""
    prefs = load_preferences(category)
    if not prefs:
        print(f"\n  No preferences for {category} yet. Rate some items first.")
        return

    sorted_tags = sorted(prefs.items(), key=lambda x: x[1], reverse=True)
    print(f"\n  Preferences for {category} ({len(sorted_tags)} tags):")
    print(f"  {'Weight':>7}  Tag")
    print(f"  {'-' * 40}")

    liked = [(t, w) for t, w in sorted_tags if w > 0]
    disliked = [(t, w) for t, w in sorted_tags if w < 0]
    neutral = [(t, w) for t, w in sorted_tags if w == 0]

    for tag, weight in liked[:15]:
        print(f"  {weight:>+7.2f}  {tag}")
    if len(liked) > 15:
        print(f"  ... +{len(liked) - 15} more liked tags")

    if disliked:
        print()
        for tag, weight in disliked[:15]:
            print(f"  {weight:>+7.2f}  {tag}")
        if len(disliked) > 15:
            print(f"  ... +{len(disliked) - 15} more disliked tags")

    if neutral:
        print(f"\n  ({len(neutral)} neutral tags)")


def cmd_replay(category: str) -> None:
    """Regenerate preferences from feedback log."""
    prefs = replay(category)
    print(f"\n  Replayed feedback log -> {len(prefs)} tags")


def cmd_log(category: str) -> None:
    """Show recent download log entries."""
    path = _log_path(category)
    if not path.exists():
        print("\n  No download log yet.")
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    # Show last 20 lines
    recent = lines[-20:] if len(lines) > 20 else lines
    print(f"\n  --- download.log (last {len(recent)} lines) ---")
    for line in recent:
        print(f"  {line}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} earlier lines)")
    print(f"  File: {path}")


# ── Interactive loop ─────────────────────────────────────────────────

MENU = """\
=== TasteBud [{category}] ===
  [1] Download   — download a gallery by URL (background)
  [2] Browse     — view & score downloaded items
  [3] Rate       — rate unrated downloaded items
  [4] Prefs      — view current preferences
  [5] Replay     — regenerate prefs from feedback log
  [6] Log        — view download progress
  [q] Quit"""


async def interactive(category: str) -> None:
    bg_tasks: list[asyncio.Task[None]] = []

    print(MENU.format(category=category))

    while True:
        try:
            cmd = (await asyncio.to_thread(input, "> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            cmd = "q"

        match cmd:
            case "1":
                # Show available sources
                source_names = list(_SOURCES.keys())
                print(f"  Sources: {', '.join(source_names)}")

                raw = (await asyncio.to_thread(
                    input, "  ID (e.g. 3796701/c3305f85d4) or full URL: "
                )).strip()
                if not raw:
                    print("  No input.")
                    continue

                parsed = _parse_gallery_input(raw)
                if not parsed:
                    print("  Could not parse input. Use: <gid>/<token> or a full URL.")
                    continue

                source, gid, token = parsed

                # If source wasn't detected from URL, ask
                if source is None:
                    if len(source_names) == 1:
                        source = source_names[0]
                    else:
                        source = (await asyncio.to_thread(
                            input, f"  Source [{'/'.join(source_names)}]: "
                        )).strip().lower()
                        if source not in _SOURCES:
                            print(f"  Unknown source: {source}")
                            continue

                task = asyncio.create_task(download_task(category, source, gid, token))
                bg_tasks.append(task)
                print(f"  Downloading {source} {gid} in background. [6] to check progress.")

            case "2":
                cmd_browse(category)

            case "3":
                await cmd_rate(category)

            case "4":
                cmd_prefs(category)

            case "5":
                cmd_replay(category)

            case "6":
                cmd_log(category)

            case "q":
                # Cancel background tasks
                for t in bg_tasks:
                    if not t.done():
                        t.cancel()
                for t in bg_tasks:
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass
                print("Bye.")
                return

            case _:
                print(MENU.format(category=category))


async def main() -> None:
    args = sys.argv[1:]
    category = DEFAULT_CATEGORY

    if "--category" in args:
        idx = args.index("--category")
        if idx + 1 < len(args):
            category = args[idx + 1]

    await interactive(category)


if __name__ == "__main__":
    asyncio.run(main())
