"""Quick test: try collecting from e-hentai and print results."""

import asyncio
import sys
from pathlib import Path

# Add src to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from collector.ehentai.collector import EHentaiCollector


async def main() -> None:
    collector = EHentaiCollector()
    print("Fetching from e-hentai.org ...")
    results = await collector.collect(page=0)

    print(f"\nGot {len(results)} galleries:\n")
    for r in results[:5]:  # Show first 5
        print(f"  [{r.source_id}] {r.title}")
        print(f"    URL: {r.url}")
        print(f"    Thumb: {r.thumbnail_url}")
        print(f"    Category: {r.metadata.get('category')}")
        print(f"    Rating: {r.metadata.get('rating')}")
        print(f"    Tags ({len(r.tags)}):")
        for tag in r.tags[:10]:
            print(f"      {tag.category}: {tag.name}")
        if len(r.tags) > 10:
            print(f"      ... and {len(r.tags) - 10} more")
        print()


asyncio.run(main())
