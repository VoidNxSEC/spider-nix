#!/usr/bin/env python3
"""Real ML feedback system demo - Track crawl attempts and adapt strategies."""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spider_nix import SpiderNix
from spider_nix.config import CrawlerConfig
from spider_nix.ml import (
    CrawlAttempt,
    FailureClass,
    FailureClassifier,
    FeedbackLogger,
    Strategy,
    StrategySelector,
)


async def demo_ml_feedback():
    """Demonstrate ML feedback system with real crawls."""
    print("🧠 Spider-Nix ML Feedback System Demo")
    print("=" * 60)
    print()

    # Initialize ML components
    logger = FeedbackLogger("demo_feedback.db")
    await logger.initialize()
    print("✓ Database initialized")

    classifier = FailureClassifier()
    selector = StrategySelector(logger, epsilon=0.3)
    print("✓ ML components loaded")
    print()

    # Test URLs
    test_urls = [
        "https://httpbin.org/status/200",  # Success
        "https://httpbin.org/status/429",  # Rate limit
        "https://httpbin.org/status/403",  # Forbidden
        "https://httpbin.org/delay/15",    # Timeout (slow)
    ]

    # Crawler
    config = CrawlerConfig()
    config.request_timeout_seconds = 10
    spider = SpiderNix(config=config)

    print("📊 Testing multiple scenarios...")
    print("-" * 60)

    for url in test_urls:
        domain = urlparse(url).netloc
        print(f"\n🎯 Testing: {url}")

        # Select strategies
        strategies = await selector.select_strategies(url, num_strategies=2)
        print(f"   Strategies: {[s.value for s in strategies]}")

        # Crawl
        start_time = datetime.now()
        try:
            results = await spider.crawl(url, max_pages=1)
            result = results[0] if results else None

            if result:
                status_code = result.status_code
                response_time_ms = result.fetch_duration_ms
                response_size = len(result.content)
            else:
                status_code = 0
                response_time_ms = 10000
                response_size = 0

        except Exception as e:
            print(f"   ❌ Error: {e}")
            status_code = 0
            response_time_ms = 10000
            response_size = 0

        # Classify failure
        failure_class = classifier.classify(
            status_code=status_code,
            response_time_ms=response_time_ms,
        )
        print(f"   Classification: {failure_class.value}")

        # Log attempt
        attempt = CrawlAttempt(
            url=url,
            domain=domain,
            status_code=status_code,
            response_time_ms=response_time_ms,
            response_size=response_size,
            failure_class=failure_class,
            strategies_used=strategies,
            timestamp=start_time,
        )
        await logger.log_attempt(attempt)

        # Update strategy effectiveness
        success = failure_class == FailureClass.SUCCESS
        for strategy in strategies:
            await logger.update_strategy_effectiveness(
                domain=domain,
                strategy=strategy,
                success=success,
                response_time_ms=response_time_ms,
            )

        # Check if should retry
        if classifier.should_retry(failure_class, attempt_number=1):
            delay_ms = classifier.get_retry_delay_ms(failure_class, attempt_number=1)
            print(f"   🔄 Should retry in {delay_ms}ms")

    # Show statistics
    print("\n" + "=" * 60)
    print("📈 Statistics")
    print("=" * 60)

    stats = await logger.get_stats()
    print(f"Total attempts: {stats['total_attempts']}")
    print(f"Success rate: {stats['success_rate']:.1%}")
    print(f"Avg response time: {stats['avg_response_time_ms']:.0f}ms")
    print(f"Unique domains: {stats['unique_domains']}")
    print()

    # Failure distribution
    distribution = await logger.get_failure_distribution()
    print("Failure distribution:")
    for failure_type, count in distribution.items():
        print(f"  {failure_type}: {count}")
    print()

    # Best strategies per domain
    print("Best strategies per domain:")
    for url in test_urls:
        domain = urlparse(url).netloc
        effectiveness = await logger.get_strategy_effectiveness(domain)

        if effectiveness:
            best = max(effectiveness, key=lambda e: e.success_rate)
            print(f"  {domain}:")
            print(f"    Strategy: {best.strategy.value}")
            print(f"    Success rate: {best.success_rate:.1%}")
            print(f"    Avg time: {best.avg_response_time_ms:.0f}ms")

    print("\n✅ Demo complete! Database: demo_feedback.db")
    print("\nQuery it:")
    print("  sqlite3 demo_feedback.db 'SELECT * FROM crawl_attempts;'")
    print("  sqlite3 demo_feedback.db 'SELECT * FROM strategy_effectiveness;'")


if __name__ == "__main__":
    asyncio.run(demo_ml_feedback())
