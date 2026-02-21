"""TasteBud: interactive async entry point.

Runs the full loop: collect → analyze → score → rate → learn.
Background collection doesn't block the interactive menu.

Usage:
    python scripts/main.py                  # interactive mode (manga)
    python scripts/main.py --category news  # different category
"""

import asyncio
import io
import sys
from pathlib import Path

# Fix Windows console encoding for CJK characters
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from analyzer.source_tag.analyzer import SourceTagAnalyzer
from collector.base import TagResult
from collector.storage import (
    find_items,
    find_unanalyzed,
    load_item,
    save_analysis,
    save_metadata,
)
from engine.feedback import load_feedback, replay, submit_feedback
from engine.preference import load_preferences
from engine.scorer import TagScorer

DEFAULT_CATEGORY = "manga"


# ── Background tasks ─────────────────────────────────────────────────

async def collector_task(category: str, search: str, pages: int = 3) -> None:
    """Fetch listings in background and save metadata to disk."""
    from collector.ehentai.collector import EHentaiCollector

    collector = EHentaiCollector()
    print(f"\n  [bg] Collecting from {collector.source}"
          f"{f' (search: {search})' if search else ''} ...")

    total = 0
    for page in range(pages):
        try:
            results = await collector.collect(page=page, search=search)
        except Exception as e:
            print(f"\n  [bg] Page {page} failed: {e}")
            break

        for r in results:
            save_metadata(r, category)
        total += len(results)
        print(f"\n  [bg] Page {page}: {len(results)} items saved (total: {total})")

        # Auto-analyze new items after each page
        await analyze_new(category)
        await asyncio.sleep(1.0)

    print(f"\n  [bg] Collection done — {total} items saved")


async def analyze_new(category: str) -> None:
    """Analyze items that have data.json but no analysis.json yet."""
    unanalyzed = find_unanalyzed(category)
    if not unanalyzed:
        return

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

    print(f"\n  [bg] Analyzed {len(unanalyzed)} new items")


# ── Foreground commands ──────────────────────────────────────────────

def cmd_browse(category: str) -> None:
    """Browse scored items — reads latest disk state."""
    scorer = TagScorer()
    prefs = load_preferences(category)
    items = find_items(category)

    if not items:
        print(f"\n  No items in {category}. Press 1 to collect first.")
        return

    # Score each item
    results: list[tuple[float, str, str, str, list[str]]] = []
    analyzer = SourceTagAnalyzer()

    for idir in items:
        content = load_item(idir)
        if not content:
            continue

        # Use analysis.json tags if available, else fall back to source tags
        analysis_file = idir / "analysis.json"
        if analysis_file.exists():
            import json
            analysis_data = json.loads(analysis_file.read_text(encoding="utf-8"))
            tags = [
                TagResult(
                    name=t["name"],
                    category=t.get("category", "general"),
                    confidence=t.get("confidence", 1.0),
                )
                for t in analysis_data.get("enriched_tags", [])
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


def cmd_rate(category: str) -> None:
    """Rate unrated items interactively."""
    items = find_items(category)
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
        print(f"\n  --- {source}/{sid} ---")
        print(f"  {content.title}")
        if content.url:
            print(f"  {content.url}")
        tag_names = [t.name for t in content.tags[:12]]
        if tag_names:
            extra = f" (+{len(content.tags) - 12})" if len(content.tags) > 12 else ""
            print(f"  Tags: {', '.join(tag_names)}{extra}")

        print("  [l]ike  [d]islike  [s]kip  [q]uit rating")
        cmd = input("  > ").strip().lower()

        if cmd in ("l", "like"):
            submit_feedback(category, source, sid, "like", content.tags)
            print("  -> liked")
        elif cmd in ("d", "dislike"):
            submit_feedback(category, source, sid, "dislike", content.tags)
            print("  -> disliked")
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

    # Show top liked
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


# ── Interactive loop ─────────────────────────────────────────────────

MENU = """\
=== TasteBud [{category}] ===
  [1] Collect    — fetch new items (background)
  [2] Browse     — view & score collected items
  [3] Rate       — rate unrated items (like/dislike)
  [4] Prefs      — view current preferences
  [5] Replay     — regenerate prefs from feedback log
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
                search = (await asyncio.to_thread(
                    input, "  Search (empty for front page): "
                )).strip()
                pages_str = (await asyncio.to_thread(
                    input, "  Pages to fetch [3]: "
                )).strip()
                pages = int(pages_str) if pages_str.isdigit() else 3

                task = asyncio.create_task(
                    collector_task(category, search, pages)
                )
                bg_tasks.append(task)
                print("  Collection started in background. Menu is ready.")

            case "2":
                cmd_browse(category)

            case "3":
                cmd_rate(category)

            case "4":
                cmd_prefs(category)

            case "5":
                cmd_replay(category)

            case "q":
                # Cancel background tasks
                for t in bg_tasks:
                    if not t.done():
                        t.cancel()
                # Wait for cancellation
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
