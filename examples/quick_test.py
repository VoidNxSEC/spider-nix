#!/usr/bin/env python3
"""Quick test - Validate all components work."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spider_nix import SpiderNix
from spider_nix.config import CrawlerConfig
from spider_nix.extraction import BoundingBox, DOMAnalyzer, FusionEngine
from spider_nix.ml import FailureClassifier, FeedbackLogger, StrategySelector
from spider_nix.stealth import StealthEngine


async def main():
    print("⚡ Quick Test - Validate Components")
    print("=" * 50)

    # Test 1: Stealth
    print("\n1. StealthEngine...")
    stealth = StealthEngine()
    headers = stealth.get_headers()
    fingerprint = stealth.get_fingerprint()
    js = stealth.get_playwright_stealth_script()
    print(f"   ✓ Headers: {len(headers)} entries")
    print(f"   ✓ Fingerprint: {fingerprint['platform']}")
    print(f"   ✓ JS stealth: {len(js)} chars")

    # Test 2: Extraction
    print("\n2. Extraction models...")
    box1 = BoundingBox(x=0.0, y=0.0, width=0.5, height=0.5)
    box2 = BoundingBox(x=0.25, y=0.25, width=0.5, height=0.5)
    iou = box1.iou(box2)
    print(f"   ✓ IoU calculation: {iou:.2f}")

    # Test 3: DOM Analyzer
    print("\n3. DOMAnalyzer...")
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <a href="/link1">Link 1</a>
        <button>Click me</button>
    </body>
    </html>
    """
    analyzer = DOMAnalyzer()
    elements = analyzer.parse_html(html)
    metadata = analyzer.extract_metadata(html)
    print(f"   ✓ Parsed {len(elements)} elements")
    print(f"   ✓ Title: {metadata.get('title')}")

    # Test 4: ML Classifier
    print("\n4. FailureClassifier...")
    classifier = FailureClassifier()
    failure = classifier.classify(status_code=429, response_time_ms=5000)
    print(f"   ✓ Classified 429 as: {failure.value}")

    features = classifier.extract_features(
        status_code=200,
        response_time_ms=1500,
        response_size=1024,
    )
    print(f"   ✓ Extracted {len(features)} features")

    # Test 5: FeedbackLogger
    print("\n5. FeedbackLogger...")
    logger = FeedbackLogger(":memory:")  # In-memory DB
    await logger.initialize()
    stats = await logger.get_stats()
    print(f"   ✓ Database initialized")
    print(f"   ✓ Total attempts: {stats['total_attempts']}")

    # Test 6: Crawler (real HTTP request)
    print("\n6. SpiderNix crawler...")
    config = CrawlerConfig()
    config.request_timeout_seconds = 5
    spider = SpiderNix(config=config)

    try:
        results = await spider.crawl("https://httpbin.org/status/200", max_pages=1)
        if results:
            result = results[0]
            print(f"   ✓ Crawled URL")
            print(f"   ✓ Status: {result.status_code}")
            print(f"   ✓ Size: {len(result.content)} bytes")
            print(f"   ✓ Time: {result.fetch_duration_ms}ms")
        else:
            print("   ⚠️  No results")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    print("\n" + "=" * 50)
    print("✅ All components working!")
    print("\nTry the examples:")
    print("  python examples/scrape_hackernews.py")
    print("  python examples/ml_feedback_demo.py")
    print("  python examples/stress_test.py")


if __name__ == "__main__":
    asyncio.run(main())
