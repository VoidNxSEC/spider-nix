"""Simplified tests for Strategy Selector (Phase 1D ML)."""

import pytest
from spider_nix.ml import StrategySelector, Strategy, FailureClass


class TestStrategySelectionBasic:
    """Basic tests for strategy selection."""

    def test_can_select_strategy(self):
        """Test that selector can select a strategy."""
        selector = StrategySelector()

        strategy = selector.select_strategy("example.com")

        # Should return a valid Strategy enum
        assert isinstance(strategy, Strategy)

    def test_can_update_stats(self):
        """Test that selector can update statistics."""
        selector = StrategySelector()

        domain = "example.com"
        strategy = Strategy.TLS_FINGERPRINT_ROTATION

        # Update with success
        selector.update(
            domain=domain,
            strategy=strategy,
            success=True,
            response_time_ms=100.0
        )

        # Stats should be updated
        stats = selector.get_stats()
        assert domain in stats
        assert strategy in stats[domain]
        assert stats[domain][strategy]["success"] == 1

    def test_multiple_updates(self):
        """Test multiple updates to same strategy."""
        selector = StrategySelector()

        domain = "example.com"
        strategy = Strategy.PROXY_ROTATION

        # 10 successful attempts
        for _ in range(10):
            selector.update(domain, strategy, True, 50.0)

        # 3 failures
        for _ in range(3):
            selector.update(domain, strategy, False, 100.0)

        stats = selector.get_stats()
        assert stats[domain][strategy]["success"] == 10
        assert stats[domain][strategy]["failure"] == 3

    def test_default_strategy_without_data(self):
        """Test that default strategy is returned when no data."""
        selector = StrategySelector()

        strategy = selector.select_strategy("new-domain.com")

        # Should return a valid strategy (fallback to default)
        assert isinstance(strategy, Strategy)

    def test_exploitation_mode(self):
        """Test exploitation (epsilon=0) selects best strategy."""
        selector = StrategySelector(epsilon=0.0)

        domain = "example.com"

        # Make one strategy clearly better
        for _ in range(20):
            selector.update(domain, Strategy.TLS_FINGERPRINT_ROTATION, True, 100.0)

        for _ in range(5):
            selector.update(domain, Strategy.PROXY_ROTATION, False, 200.0)

        # Should always select the better strategy
        selected = [selector.select_strategy(domain) for _ in range(5)]

        # All should be TLS_FINGERPRINT_ROTATION
        assert all(s == Strategy.TLS_FINGERPRINT_ROTATION for s in selected)

    def test_exploration_mode(self):
        """Test exploration (epsilon=1.0) explores all strategies."""
        selector = StrategySelector(epsilon=1.0)

        domain = "example.com"

        # Even with one clearly better strategy
        for _ in range(50):
            selector.update(domain, Strategy.TLS_FINGERPRINT_ROTATION, True, 100.0)

        # Should still explore (random selection)
        selected = [selector.select_strategy(domain) for _ in range(20)]
        unique = set(selected)

        # Should have explored multiple strategies
        assert len(unique) >= 2, "Should explore with epsilon=1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
