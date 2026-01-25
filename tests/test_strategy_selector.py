"""Unit tests for Strategy Selector (Phase 1D ML - Epsilon-Greedy Bandit)."""

import pytest
from spider_nix.ml import StrategySelector, Strategy, FailureClass


class TestStrategySelection:
    """Test strategy selection logic (epsilon-greedy)."""

    def test_initial_strategy_random(self):
        """Test that initial strategy is random (no data yet)."""
        selector = StrategySelector(epsilon=0.1)

        strategies = []
        for _ in range(10):
            strategy = selector.select_strategy("example.com")
            strategies.append(strategy)

        # Should have some variety (not all the same)
        unique_strategies = set(strategies)
        assert len(unique_strategies) >= 2, "Should explore different strategies initially"

    def test_record_success_updates_stats(self):
        """Test that successful attempts update statistics."""
        selector = StrategySelector(epsilon=0.0)  # No exploration, pure exploitation

        domain = "example.com"
        strategy = Strategy.TLS_FINGERPRINT_ROTATION

        # Record 10 successful attempts
        for _ in range(10):
            selector.record_attempt(
                domain=domain,
                strategy=strategy,
                failure_class=FailureClass.SUCCESS,
                response_time_ms=100.0
            )

        # Check stats were updated
        stats = selector.strategy_stats[domain][strategy]
        assert stats["success"] == 10
        assert stats["failure"] == 0
        assert stats["avg_response_time"] > 0

    def test_record_failure_updates_stats(self):
        """Test that failed attempts update statistics."""
        selector = StrategySelector(epsilon=0.0)

        domain = "example.com"
        strategy = Strategy.PROXY_ROTATION

        # Record 5 failures
        for _ in range(5):
            selector.record_attempt(
                domain=domain,
                strategy=strategy,
                failure_class=FailureClass.RATE_LIMIT,
                response_time_ms=50.0
            )

        stats = selector.strategy_stats[domain][strategy]
        assert stats["success"] == 0
        assert stats["failure"] == 5

    def test_exploitation_selects_best_strategy(self):
        """Test that exploitation phase selects best performing strategy."""
        selector = StrategySelector(epsilon=0.0)  # Pure exploitation

        domain = "example.com"

        # Make TLS_FINGERPRINT_ROTATION very successful
        for _ in range(20):
            selector.record_attempt(
                domain, Strategy.TLS_FINGERPRINT_ROTATION,
                FailureClass.SUCCESS, 100.0
            )

        # Make PROXY_ROTATION fail
        for _ in range(10):
            selector.record_attempt(
                domain, Strategy.PROXY_ROTATION,
                FailureClass.RATE_LIMIT, 200.0
            )

        # Should consistently pick TLS_FINGERPRINT_ROTATION
        selected_strategies = [selector.select_strategy(domain) for _ in range(10)]

        # All should be TLS_FINGERPRINT_ROTATION
        assert all(s == Strategy.TLS_FINGERPRINT_ROTATION for s in selected_strategies), \
            "Should exploit best strategy when epsilon=0"

    def test_exploration_with_epsilon(self):
        """Test that exploration happens with epsilon > 0."""
        selector = StrategySelector(epsilon=1.0)  # 100% exploration

        domain = "example.com"

        # Make one strategy clearly better
        for _ in range(50):
            selector.record_attempt(
                domain, Strategy.TLS_FINGERPRINT_ROTATION,
                FailureClass.SUCCESS, 100.0
            )

        # With epsilon=1.0, should still explore (random selection)
        selected_strategies = [selector.select_strategy(domain) for _ in range(20)]
        unique = set(selected_strategies)

        # Should have explored multiple strategies
        assert len(unique) >= 3, "Should explore different strategies with high epsilon"

    def test_multiple_domains_independent(self):
        """Test that different domains have independent statistics."""
        selector = StrategySelector(epsilon=0.0)

        # Domain A: TLS rotation works
        for _ in range(10):
            selector.record_attempt(
                "domainA.com", Strategy.TLS_FINGERPRINT_ROTATION,
                FailureClass.SUCCESS, 100.0
            )

        # Domain B: Proxy rotation works
        for _ in range(10):
            selector.record_attempt(
                "domainB.com", Strategy.PROXY_ROTATION,
                FailureClass.SUCCESS, 100.0
            )

        # Should select different strategies for each domain
        strategy_a = selector.select_strategy("domainA.com")
        strategy_b = selector.select_strategy("domainB.com")

        assert strategy_a == Strategy.TLS_FINGERPRINT_ROTATION
        assert strategy_b == Strategy.PROXY_ROTATION

    def test_get_domain_stats(self):
        """Test retrieving statistics for a domain."""
        selector = StrategySelector()

        domain = "example.com"
        selector.record_attempt(
            domain, Strategy.BROWSER_MODE,
            FailureClass.SUCCESS, 150.0
        )

        stats = selector.get_domain_stats(domain)

        assert domain in stats
        assert Strategy.BROWSER_MODE in stats[domain]
        assert stats[domain][Strategy.BROWSER_MODE]["success"] == 1


class TestStrategyRecommendations:
    """Test strategy recommendation logic."""

    def test_recommend_strategies_for_rate_limit(self):
        """Test recommendations when rate limited."""
        selector = StrategySelector()

        recommendations = selector.recommend_strategies(FailureClass.RATE_LIMIT)

        # Should include EXTENDED_DELAYS and PROXY_ROTATION
        assert Strategy.EXTENDED_DELAYS in recommendations
        assert Strategy.PROXY_ROTATION in recommendations

    def test_recommend_strategies_for_captcha(self):
        """Test recommendations when CAPTCHA detected."""
        selector = StrategySelector()

        recommendations = selector.recommend_strategies(FailureClass.CAPTCHA)

        # Should include BROWSER_MODE and delays
        assert Strategy.BROWSER_MODE in recommendations
        assert Strategy.EXTENDED_DELAYS in recommendations

    def test_recommend_strategies_for_fingerprint(self):
        """Test recommendations when fingerprint detected."""
        selector = StrategySelector()

        recommendations = selector.recommend_strategies(FailureClass.FINGERPRINT_DETECTED)

        # Should include TLS rotation and headers variation
        assert Strategy.TLS_FINGERPRINT_ROTATION in recommendations
        assert Strategy.HEADERS_VARIATION in recommendations


class TestConvergence:
    """Test learning convergence behavior."""

    def test_converges_to_best_strategy(self):
        """Test that selector converges to best strategy over time."""
        selector = StrategySelector(epsilon=0.1)  # 10% exploration

        domain = "example.com"

        # Simulate 100 attempts with different success rates
        # TLS rotation: 80% success
        # Proxy rotation: 30% success
        # Others: 50% success

        for i in range(100):
            # TLS rotation (80% success)
            if i % 10 < 8:
                selector.record_attempt(
                    domain, Strategy.TLS_FINGERPRINT_ROTATION,
                    FailureClass.SUCCESS, 100.0
                )
            else:
                selector.record_attempt(
                    domain, Strategy.TLS_FINGERPRINT_ROTATION,
                    FailureClass.RATE_LIMIT, 100.0
                )

            # Proxy rotation (30% success)
            if i % 10 < 3:
                selector.record_attempt(
                    domain, Strategy.PROXY_ROTATION,
                    FailureClass.SUCCESS, 100.0
                )
            else:
                selector.record_attempt(
                    domain, Strategy.PROXY_ROTATION,
                    FailureClass.FINGERPRINT_DETECTED, 100.0
                )

        # After learning, should mostly select TLS_FINGERPRINT_ROTATION
        selected = [selector.select_strategy(domain) for _ in range(20)]
        tls_count = sum(1 for s in selected if s == Strategy.TLS_FINGERPRINT_ROTATION)

        # Should pick best strategy at least 70% of time (accounting for 10% epsilon)
        assert tls_count >= 14, f"Should converge to best strategy, got {tls_count}/20"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
