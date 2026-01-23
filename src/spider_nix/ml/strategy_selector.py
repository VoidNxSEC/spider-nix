"""Strategy selector using multi-armed bandit algorithm.

Learns which evasion strategies work best per domain.
"""

import random
from urllib.parse import urlparse

from .feedback_logger import FeedbackLogger
from .models import Strategy


class StrategySelector:
    """Select best evasion strategies using epsilon-greedy bandit.

    Balances exploration (trying new strategies) with exploitation
    (using known good strategies).
    """

    def __init__(
        self,
        feedback_logger: FeedbackLogger,
        epsilon: float = 0.2,
        default_strategies: list[Strategy] | None = None,
    ):
        """Initialize strategy selector.

        Args:
            feedback_logger: Feedback logger for accessing effectiveness data
            epsilon: Exploration rate (0-1). Higher = more exploration.
            default_strategies: Strategies to use when no data available
        """
        self.feedback_logger = feedback_logger
        self.epsilon = epsilon
        self.default_strategies = default_strategies or [
            Strategy.TLS_FINGERPRINT_ROTATION,
            Strategy.PROXY_ROTATION,
            Strategy.HEADERS_VARIATION,
        ]
        self._rng = random.Random()

    async def select_strategies(
        self,
        url: str,
        num_strategies: int = 3,
    ) -> list[Strategy]:
        """Select strategies for a URL using epsilon-greedy.

        Args:
            url: Target URL
            num_strategies: Number of strategies to select

        Returns:
            List of selected strategies
        """
        domain = self._extract_domain(url)

        # Get effectiveness data for this domain
        effectiveness = await self.feedback_logger.get_strategy_effectiveness(domain)

        # No data - use defaults with random exploration
        if not effectiveness:
            return self._explore_random(num_strategies)

        # Epsilon-greedy selection
        if self._rng.random() < self.epsilon:
            # Explore: try random strategies
            return self._explore_random(num_strategies)
        else:
            # Exploit: use best performing strategies
            return self._exploit_best(effectiveness, num_strategies)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain (e.g., 'example.com')
        """
        parsed = urlparse(url)
        return parsed.netloc

    def _explore_random(self, num_strategies: int) -> list[Strategy]:
        """Select random strategies for exploration.

        Args:
            num_strategies: Number to select

        Returns:
            Random strategies
        """
        all_strategies = list(Strategy)
        selected = self._rng.sample(
            all_strategies,
            min(num_strategies, len(all_strategies)),
        )
        return selected

    def _exploit_best(
        self,
        effectiveness: list,
        num_strategies: int,
    ) -> list[Strategy]:
        """Select best performing strategies.

        Args:
            effectiveness: List of StrategyEffectiveness records
            num_strategies: Number to select

        Returns:
            Best strategies
        """
        # Sort by success rate (descending), then by response time (ascending)
        sorted_strategies = sorted(
            effectiveness,
            key=lambda e: (e.success_rate, -e.avg_response_time_ms),
            reverse=True,
        )

        # Take top N
        best = sorted_strategies[:num_strategies]

        # Add exploration if we don't have enough
        if len(best) < num_strategies:
            tried = {e.strategy for e in best}
            untried = [s for s in Strategy if s not in tried]

            if untried:
                additional = self._rng.sample(
                    untried,
                    min(num_strategies - len(best), len(untried)),
                )
                best.extend([
                    type('Effectiveness', (), {
                        'strategy': s,
                        'success_rate': 0.0,
                        'avg_response_time_ms': 0.0,
                    })()
                    for s in additional
                ])

        return [e.strategy for e in best[:num_strategies]]

    async def get_best_single_strategy(self, url: str) -> Strategy:
        """Get single best strategy for a URL.

        Args:
            url: Target URL

        Returns:
            Best strategy
        """
        strategies = await self.select_strategies(url, num_strategies=1)
        return strategies[0] if strategies else self.default_strategies[0]

    async def should_change_strategy(
        self,
        url: str,
        current_strategies: list[Strategy],
        consecutive_failures: int,
    ) -> bool:
        """Determine if strategy should be changed after failures.

        Args:
            url: Target URL
            current_strategies: Currently active strategies
            consecutive_failures: Number of consecutive failures

        Returns:
            Whether to change strategy
        """
        # Change after 3 consecutive failures
        if consecutive_failures >= 3:
            return True

        # Check if current strategies have low success rate
        domain = self._extract_domain(url)
        effectiveness = await self.feedback_logger.get_strategy_effectiveness(domain)

        if not effectiveness:
            return False

        # Map to dict for lookup
        eff_map = {e.strategy: e for e in effectiveness}

        # Check if any current strategy has <30% success rate
        for strategy in current_strategies:
            if strategy in eff_map:
                if eff_map[strategy].success_rate < 0.3:
                    return True

        return False

    def set_epsilon(self, epsilon: float):
        """Update exploration rate.

        Args:
            epsilon: New exploration rate (0-1)
        """
        if not 0 <= epsilon <= 1:
            raise ValueError("Epsilon must be between 0 and 1")
        self.epsilon = epsilon

    async def get_strategy_recommendations(
        self,
        url: str,
    ) -> dict[str, list[tuple[Strategy, float]]]:
        """Get strategy recommendations with confidence scores.

        Args:
            url: Target URL

        Returns:
            Dictionary with 'recommended' and 'avoid' strategies
        """
        domain = self._extract_domain(url)
        effectiveness = await self.feedback_logger.get_strategy_effectiveness(domain)

        if not effectiveness:
            return {
                "recommended": [(s, 0.5) for s in self.default_strategies],
                "avoid": [],
            }

        # Strategies with >60% success rate
        recommended = [
            (e.strategy, e.success_rate)
            for e in effectiveness
            if e.success_rate >= 0.6 and e.total_attempts >= 5
        ]

        # Strategies with <30% success rate
        avoid = [
            (e.strategy, e.success_rate)
            for e in effectiveness
            if e.success_rate < 0.3 and e.total_attempts >= 5
        ]

        return {
            "recommended": sorted(recommended, key=lambda x: x[1], reverse=True),
            "avoid": sorted(avoid, key=lambda x: x[1]),
        }
