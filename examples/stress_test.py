#!/usr/bin/env python3
"""Real stress test - Test rate limiting, circuit breaker, adaptive delays."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spider_nix import SpiderNix
from spider_nix.config import CrawlerConfig


async def stress_test():
    """Stress test the crawler's resilience features."""
    print("⚡ Spider-Nix Stress Test")
    print("=" * 60)
    print("Testing: Rate limiting, Circuit breaker, Adaptive delays")
    print()

    # Config with all protections enabled
    config = CrawlerConfig()
    config.stealth.enabled = True
    config.stealth.min_delay_ms = 500
    config.stealth.max_delay_ms = 2000
    config.request_timeout_seconds = 5

    spider = SpiderNix(
        config=config,
        enable_adaptive_rate_limiting=True,
        enable_circuit_breaker=True,
        enable_deduplication=True,
    )

    # Test 1: Rapid fire requests (rate limiter should kick in)
    print("🔥 Test 1: Rapid fire requests (100 requests)")
    print("-" * 60)

    urls = [f"https://httpbin.org/delay/0?req={i}" for i in range(100)]

    start = time.time()
    success_count = 0
    failure_count = 0

    for i, url in enumerate(urls[:20], 1):  # Test first 20
        try:
            results = await spider.crawl(url, max_pages=1)
            if results and results[0].status_code == 200:
                success_count += 1
                print(f"  [{i}/20] ✓ Success", end="\r")
            else:
                failure_count += 1
                print(f"  [{i}/20] ❌ Failed", end="\r")
        except Exception as e:
            failure_count += 1
            print(f"  [{i}/20] ❌ Error: {str(e)[:40]}", end="\r")

        # Small delay to see rate limiter adapt
        if i % 5 == 0:
            await asyncio.sleep(0.1)

    elapsed = time.time() - start
    print()
    print(f"\nResults:")
    print(f"  Successes: {success_count}")
    print(f"  Failures: {failure_count}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Avg time per request: {elapsed/20:.2f}s")

    # Show rate limiter stats
    if spider.rate_limiter:
        current_delay = spider.rate_limiter.get_delay_ms()
        print(f"  Current delay: {current_delay}ms")
        print(f"  Success rate: {spider.rate_limiter.success_rate:.1%}")

    print()

    # Test 2: Circuit breaker (trigger with 403s)
    print("🔌 Test 2: Circuit breaker (trigger with errors)")
    print("-" * 60)

    error_urls = ["https://httpbin.org/status/503" for _ in range(10)]

    circuit_triggered = False
    for i, url in enumerate(error_urls, 1):
        try:
            results = await spider.crawl(url, max_pages=1)
            print(f"  [{i}/10] Status: {results[0].status_code if results else 'N/A'}")
        except Exception as e:
            error_str = str(e)
            if "Circuit breaker" in error_str:
                circuit_triggered = True
                print(f"  [{i}/10] ⚠️  Circuit breaker OPEN")
                break
            print(f"  [{i}/10] ❌ {error_str[:50]}")

    if circuit_triggered:
        print("\n  ✓ Circuit breaker triggered successfully")
    else:
        print("\n  ⚠️  Circuit breaker did not trigger")

    # Show circuit breaker stats
    if spider.circuit_breaker:
        stats = spider.circuit_breaker.get_stats()
        print(f"  Failure rate: {stats['failure_rate']:.1%}")
        print(f"  State: {stats['state']}")
        print(f"  Total calls: {stats['total_calls']}")
        print(f"  Failed calls: {stats['failed_calls']}")

    print()

    # Test 3: Deduplication
    print("🔄 Test 3: Deduplication")
    print("-" * 60)

    dup_url = "https://httpbin.org/anything"
    print(f"  Requesting same URL 5 times: {dup_url}")

    actual_requests = 0
    for i in range(5):
        try:
            results = await spider.crawl(dup_url, max_pages=1)
            if results:
                actual_requests += 1
                print(f"  [{i+1}/5] ✓ Fetched (actual request made)")
            else:
                print(f"  [{i+1}/5] ⚠️  Deduplicated (cached)")
        except Exception as e:
            print(f"  [{i+1}/5] ❌ {str(e)[:50]}")

    print(f"\n  Expected: 1 actual request, 4 deduplicated")
    print(f"  Actual: {actual_requests} request(s)")

    if actual_requests > 1:
        print("  ⚠️  Deduplication may not be working")
    else:
        print("  ✓ Deduplication working")

    print()
    print("=" * 60)
    print("✅ Stress test complete!")


if __name__ == "__main__":
    asyncio.run(stress_test())
