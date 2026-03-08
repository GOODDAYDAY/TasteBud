"""TasteBud: interactive async entry point.

Runs the full loop: search → sieve → download → analyze → score → rate → learn.
Background search+sieve pipeline doesn't block the interactive menu.

Usage:
    python scripts/main.py                  # interactive mode (manga)
    python scripts/main.py --category news  # different category
"""

import asyncio
import io
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
)
from engine.feedback import load_feedback, replay, submit_feedback
from engine.preference import load_preferences
from engine.scorer import TagScorer
from engine.sieve import (
    SieveResult,
    load_sieve,
    record_layer3,
    save_sieve,
)

DEFAULT_CATEGORY = "manga"


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
  [1] Browse     — view sieved items ranked by score
  [2] Rate       — evaluate items (Layer 3)
  [3] Prefs      — view current preferences
  [4] Replay     — regenerate prefs from feedback log
  [5] Log        — view background task log
  [q] Quit"""


async def interactive(category: str) -> None:
    print(MENU.format(category=category))

    while True:
        try:
            cmd = (await asyncio.to_thread(input, "> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            cmd = "q"

        match cmd:
            case "1":
                cmd_browse(category)

            case "2":
                await cmd_rate(category)

            case "3":
                cmd_prefs(category)

            case "4":
                cmd_replay(category)

            case "5":
                cmd_log(category)

            case "q":
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
