#!/usr/bin/env python3
"""Real scraping example - Hacker News front page with anti-detection."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spider_nix import SpiderNix
from spider_nix.config import CrawlerConfig
from spider_nix.extraction import DOMAnalyzer


async def scrape_hackernews():
    """Scrape HackerNews front page stories."""
    print("🕸️  Spider-Nix - Real Scraping Demo")
    print("=" * 50)
    print("Target: news.ycombinator.com")
    print()

    # Config with stealth
    config = CrawlerConfig()
    config.stealth.enabled = True
    config.stealth.min_delay_ms = 1000
    config.stealth.max_delay_ms = 3000

    # Create crawler
    spider = SpiderNix(config=config)

    # Crawl
    print("📡 Fetching https://news.ycombinator.com...")
    results = await spider.crawl(
        "https://news.ycombinator.com",
        max_pages=1,
        follow_links=False,
    )

    if not results:
        print("❌ No results")
        return

    result = results[0]
    print(f"✓ Status: {result.status_code}")
    print(f"✓ Size: {len(result.content)} bytes")
    print(f"✓ Time: {result.fetch_duration_ms}ms")
    print()

    # Parse with DOMAnalyzer
    print("🔍 Parsing DOM...")
    analyzer = DOMAnalyzer()

    # Get metadata
    metadata = analyzer.extract_metadata(result.content)
    print(f"Title: {metadata.get('title', 'N/A')}")
    print()

    # Extract all links
    links = analyzer.extract_links(result.content, base_url=result.url)
    print(f"📎 Found {len(links)} links")
    print()

    # Parse DOM elements
    elements = analyzer.parse_html(result.content, base_url=result.url)

    # Find story titles (links with class='titleline')
    stories = []
    for elem in elements:
        if elem.tag_name == "a" and "titleline" in elem.css_selector:
            if elem.text_content:
                stories.append({
                    "title": elem.text_content.strip(),
                    "url": elem.attributes.get("href", ""),
                })

    print(f"📰 Top Stories ({len(stories)}):")
    print("-" * 50)
    for i, story in enumerate(stories[:10], 1):
        print(f"{i}. {story['title'][:70]}")
        print(f"   {story['url'][:60]}")
        print()

    print("✅ Scraping complete!")


if __name__ == "__main__":
    asyncio.run(scrape_hackernews())
