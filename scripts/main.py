"""TasteBud: interactive async entry point.

Runs the full loop: search → sieve → download → analyze → score → rate → learn.
Background search+sieve pipeline doesn't block the interactive menu.

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
    find_sieved,
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
from engine.sieve import (
    SieveResult,
    load_sieve,
    record_layer3,
    run_layer1,
    run_layer2,
    save_sieve,
)

DEFAULT_CATEGORY = "manga"

# Source registry: name -> (url_regex, url_builder)
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


async def search_and_sieve_task(category: str, query: str, pages: int) -> None:
    """Search + Layer 1 sieve + download passed + Layer 2 sieve. Runs in background."""
    from collector.ehentai.collector import EHentaiCollector
    from core.config import settings

    log = lambda msg: _log(category, msg)
    collector = EHentaiCollector()
    prefs = load_preferences(category)

    # Try loading CLIP baseline (optional)
    clip_baseline = None
    try:
        from analyzer.clip.analyzer import load_baseline
        clip_baseline = load_baseline(category)
    except ImportError:
        pass

    total_candidates = 0
    layer1_passed_items = []

    log(f"Search: '{query}' ({pages} pages)")

    # ── Layer 1: Quick Sieve ─────────────────────────────────────────
    for page in range(pages):
        try:
            results = await collector.collect(page=page, search=query)
        except Exception as e:
            log(f"Page {page}: collection error: {e}")
            continue

        total_candidates += len(results)

        passed_this_page = 0
        for content in results:
            # Save metadata so item dir exists
            save_metadata(content, category)

            layer1 = await run_layer1(
                content, prefs, settings.sieve_layer1_threshold, clip_baseline,
            )

            # Save sieve result
            sieve = load_sieve(category, content.source, content.source_id) or SieveResult()
            sieve.layer1 = layer1
            save_sieve(category, content.source, content.source_id, sieve)

            if layer1.passed:
                passed_this_page += 1
                layer1_passed_items.append(content)

        log(f"Page {page}: {len(results)} items -> Layer 1 -> {passed_this_page} passed")
        if page < pages - 1:
            await asyncio.sleep(2.0)  # Rate limit between pages

    log(f"Layer 1 done: {total_candidates} candidates -> {len(layer1_passed_items)} passed")

    if not layer1_passed_items:
        log("Pipeline done: no items passed Layer 1")
        return

    # ── Download images for passed items ─────────────────────────────
    from download_gallery import _HEADERS, download_images
    import httpx

    log(f"Downloading {len(layer1_passed_items)} items ...")

    downloaded_items = []
    async with httpx.AsyncClient(headers=_HEADERS, timeout=60.0) as client:
        for content in layer1_passed_items:
            if not content.url:
                continue
            try:
                img_dir = images_dir(category, content.source, content.source_id)
                dl_count, skip_count, fail_count = await download_images(
                    client, content.url, img_dir, log=log,
                )
                save_download_result(
                    category, content.source, content.source_id,
                    dl_count, skip_count, fail_count,
                )
                downloaded_items.append(content)
                log(f"  {content.source_id}: {dl_count} images downloaded")
            except Exception as e:
                log(f"  {content.source_id}: download failed: {e}")

    if not downloaded_items:
        log("Pipeline done: no items downloaded successfully")
        return

    # ── Layer 2: Deep Scan (VLM) ─────────────────────────────────────
    log(f"Layer 2 analyzing {len(downloaded_items)} items ...")
    layer2_passed = 0

    for content in downloaded_items:
        img_path = images_dir(category, content.source, content.source_id)
        layer2 = await run_layer2(
            content, img_path, settings.sieve_layer2_threshold,
            settings.ollama_base_url, settings.ollama_model,
        )

        sieve = load_sieve(category, content.source, content.source_id) or SieveResult()
        sieve.layer2 = layer2
        save_sieve(category, content.source, content.source_id, sieve)

        if layer2.passed:
            layer2_passed += 1

        # Also run source tag analysis
        await _analyze_item(category, content, img_path)

    log(
        f"Pipeline done: {total_candidates} -> "
        f"{len(layer1_passed_items)} -> {layer2_passed} passed"
    )


async def _analyze_item(category: str, content, img_path: Path) -> None:
    """Run SourceTagAnalyzer on an item (always available, no model needed)."""
    from analyzer.source_tag.analyzer import SourceTagAnalyzer

    analyzer = SourceTagAnalyzer()
    analysis = await analyzer.analyze(
        content, img_path if img_path.exists() else None
    )
    save_analysis(category, content.source, content.source_id, analysis)


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


async def _rebuild_clip_baseline(category: str) -> None:
    """Rebuild CLIP taste baseline from all liked items' thumbnails/images.

    Scans liked items, computes CLIP embeddings, averages into baseline.
    Silently skips if sentence-transformers is not installed.
    """
    try:
        from analyzer.clip.analyzer import CLIPAnalyzer, save_baseline
    except ImportError:
        return  # CLIP not installed, skip silently

    from engine.feedback import load_feedback_log

    log_entries = load_feedback_log(category)
    liked_ids = {
        (e["source"], e["source_id"])
        for e in log_entries
        if e["rating"] == "like"
    }
    if not liked_ids:
        return

    print(f"  Updating CLIP baseline from {len(liked_ids)} liked items ...")

    try:
        analyzer = CLIPAnalyzer()
    except ImportError:
        print("  CLIP skipped (sentence-transformers not installed)")
        return
    embeddings: list[list[float]] = []

    for source, source_id in liked_ids:
        img_dir = images_dir(category, source, source_id)
        if not img_dir.exists():
            continue

        # Pick first image as representative
        extensions = {".jpg", ".jpeg", ".png", ".webp"}
        sample = next(
            (p for p in sorted(img_dir.iterdir()) if p.suffix.lower() in extensions),
            None,
        )
        if sample:
            try:
                emb = await asyncio.to_thread(analyzer.embed_image, sample)
                embeddings.append(emb)
            except Exception:
                pass  # Skip failed embeddings

    if embeddings:
        baseline = CLIPAnalyzer.update_baseline(embeddings)
        save_baseline(category, baseline)
        print(f"  CLIP baseline updated ({len(embeddings)} embeddings)")
    else:
        print("  No images available for CLIP baseline")


# ── Foreground commands ──────────────────────────────────────────────

def cmd_browse(category: str) -> None:
    """Browse sieved items ranked by score.

    Shows items that passed at least Layer 1, sorted by combined sieve score.
    Falls back to showing all downloaded items if none are sieved.
    """
    scorer = TagScorer()
    prefs = load_preferences(category)

    # Try sieved items first (passed layer 1)
    sieved_paths = find_sieved(category, 1, True)
    if sieved_paths:
        items = sieved_paths
        label = "sieved"
    else:
        items = find_downloaded(category)
        label = "downloaded"

    if not items:
        print(f"\n  No items in {category}.")
        return

    results: list[tuple[float, float, str, str, str, str, list[str]]] = []

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

        # Load sieve data for display
        sieve = load_sieve(category, content.source, content.source_id)
        sieve_score = 0.0
        sieve_status = ""
        if sieve:
            if sieve.layer2 and sieve.layer2.passed is not None:
                sieve_score = sieve.layer2.score
                sieve_status = "L2" if sieve.layer2.passed else "L2x"
            elif sieve.layer1:
                sieve_score = sieve.layer1.score
                sieve_status = "L1" if sieve.layer1.passed else "L1x"
            if sieve.layer3:
                rating = sieve.layer3.details.get("rating", "")
                sieve_status += f" {rating}"

        results.append((
            sieve_score, score, sieve_status,
            content.source, content.source_id, content.title, matched,
        ))

    results.sort(key=lambda x: (x[0], x[1]), reverse=True)

    print(f"\n  Category: {category}  |  {len(results)} {label} items  |  {len(prefs)} pref tags")
    print(f"  {'Sieve':>7}  {'Tag':>6}  {'Layer':>6}  {'ID':>10}  Title")
    print(f"  {'-' * 80}")
    for sieve_score, tag_score, status, source, sid, title, matched in results:
        title_short = title[:40] + "..." if len(title) > 40 else title
        print(
            f"  {sieve_score:>7.3f}  {tag_score:>+6.2f}  {status:>6}  "
            f"{sid:>10}  {title_short}"
        )


async def cmd_rate(category: str) -> None:
    """Rate items that passed sieve layers (Layer 3: User Evaluation).

    Prefers items that passed Layer 2 > Layer 1 > any downloaded.
    """
    # Find ratable items: prefer sieved, fall back to downloaded
    sieved_l2 = find_sieved(category, 2, True)
    sieved_l1 = find_sieved(category, 1, True)
    all_downloaded = find_downloaded(category)

    # Use best available set, deduplicated
    seen: set[str] = set()
    items: list[Path] = []
    for pool in [sieved_l2, sieved_l1, all_downloaded]:
        for p in pool:
            key = str(p)
            if key not in seen:
                seen.add(key)
                items.append(p)

    if not items:
        print(f"\n  No items in {category}.")
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

        # Show sieve info
        sieve = load_sieve(category, source, sid)
        sieve_info = ""
        if sieve:
            parts = []
            if sieve.layer1:
                parts.append(f"L1={sieve.layer1.score:.3f}")
            if sieve.layer2:
                parts.append(f"L2={sieve.layer2.score:.3f}")
            sieve_info = f"  Sieve: {' | '.join(parts)}"

        print(f"\n  --- {source}/{sid} ---")
        print(f"  {content.title}")
        if content.url:
            print(f"  {content.url}")
        if sieve_info:
            print(sieve_info)
        tag_names = [t.name for t in content.tags[:12]]
        if tag_names:
            extra = f" (+{len(content.tags) - 12})" if len(content.tags) > 12 else ""
            print(f"  Tags: {', '.join(tag_names)}{extra}")

        print("  [l]ike  [d]islike  [s]kip  [q]uit rating")
        cmd = (await asyncio.to_thread(input, "  > ")).strip().lower()

        if cmd in ("l", "like"):
            submit_feedback(category, source, sid, "like", content.tags)
            # Record in sieve.json
            if sieve is None:
                sieve = SieveResult()
            sieve.layer3 = record_layer3("like")
            save_sieve(category, source, sid, sieve)
            print("  -> liked")
        elif cmd in ("d", "dislike"):
            submit_feedback(category, source, sid, "dislike", content.tags)
            # Record in sieve.json
            if sieve is None:
                sieve = SieveResult()
            sieve.layer3 = record_layer3("dislike")
            save_sieve(category, source, sid, sieve)
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

    # Rebuild CLIP baseline from all liked items (if CLIP is installed)
    await _rebuild_clip_baseline(category)


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
    # Show last 30 lines
    recent = lines[-30:] if len(lines) > 30 else lines
    print(f"\n  --- download.log (last {len(recent)} lines) ---")
    for line in recent:
        print(f"  {line}")
    if len(lines) > 30:
        print(f"  ... ({len(lines) - 30} earlier lines)")
    print(f"  File: {path}")


# ── Interactive loop ─────────────────────────────────────────────────

MENU = """\
=== TasteBud [{category}] ===
  [1] Search     — search & auto-sieve (background)
  [2] Download   — download a gallery by URL
  [3] Browse     — view sieved items ranked by score
  [4] Rate       — evaluate items (Layer 3)
  [5] Prefs      — view current preferences
  [6] Replay     — regenerate prefs from feedback log
  [7] Log        — view background task log
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
                # Search & auto-sieve
                query = (await asyncio.to_thread(
                    input, "  Search: "
                )).strip()
                if not query:
                    print("  No query.")
                    continue

                pages_str = (await asyncio.to_thread(
                    input, "  Pages [1]: "
                )).strip()
                pages = int(pages_str) if pages_str.isdigit() else 1

                task = asyncio.create_task(
                    search_and_sieve_task(category, query, pages)
                )
                bg_tasks.append(task)
                print(f"  Searching in background... [7] to check progress.")

            case "2":
                # Direct download by URL
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
                print(f"  Downloading {source} {gid} in background. [7] to check progress.")

            case "3":
                cmd_browse(category)

            case "4":
                await cmd_rate(category)

            case "5":
                cmd_prefs(category)

            case "6":
                cmd_replay(category)

            case "7":
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
