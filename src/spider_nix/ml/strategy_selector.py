"""
Strategy Selector - Epsilon-Greedy Multi-Armed Bandit.

Learns which evasion strategies work best per domain using reinforcement learning.
Balances exploration (trying new strategies) with exploitation (using known best).

Strategies:
- TLS_FINGERPRINT_ROTATION: Rotate TLS fingerprints via Go proxy
- PROXY_ROTATION: Rotate IP addresses
- BROWSER_MODE: Use Playwright instead of httpx
- EXTENDED_DELAYS: Add longer delays between requests
- HEADERS_VARIATION: Randomize HTTP headers
- COOKIE_PERSISTENCE: Maintain cookies across requests
"""

import random
from typing import Dict, List

import aiosqlite

from .models import Strategy, FailureClass


class StrategySelector:
    """
    Epsilon-greedy multi-armed bandit for adaptive strategy selection.
    
    Algorithm:
    - With probability ε (epsilon): EXPLORE - random strategy
    - With probability (1-ε): EXPLOIT - best known strategy
    
    Learns from feedback.db which strategies succeed per domain.
    """

    def __init__(self, epsilon: float = 0.1, db_path: str = "feedback.db"):
        """
        Initialize strategy selector.
        
        Args:
            epsilon: Exploration rate (0.1 = 10% exploration, 90% exploitation)
            db_path: Path to feedback.db for loading historical stats
        """
        self.epsilon = epsilon
        self.db_path = db_path
        
        # Strategy statistics: {domain: {strategy: {"success": int, "failure": int}}}
        self.strategy_stats: Dict[str, Dict[Strategy, dict]] = {}
        
        # Default strategy (used for new domains)
        self.default_strategy = Strategy.TLS_FINGERPRINT_ROTATION

    def select_strategy(self, domain: str) -> Strategy:
        """
        Select best strategy for domain using epsilon-greedy.
        
        Args:
            domain: Target domain
            
        Returns:
            Selected strategy
        """
        # Initialize domain if new
        if domain not in self.strategy_stats:
            self._initialize_domain(domain)

        # Epsilon-greedy decision
        if random.random() < self.epsilon:
            # EXPLORE: Random strategy
            return random.choice(list(Strategy))
        else:
            # EXPLOIT: Best strategy
            return self._best_strategy(domain)

    def update(self, domain: str, strategy: Strategy, success: bool, response_time_ms: float = 0.0):
        """
        Update strategy statistics after request.

        Args:
            domain: Target domain
            strategy: Strategy used
            success: Whether request succeeded
            response_time_ms: Response time in milliseconds (optional, for future metrics)
        """
        if domain not in self.strategy_stats:
            self._initialize_domain(domain)

        if success:
            self.strategy_stats[domain][strategy]["success"] += 1
        else:
            self.strategy_stats[domain][strategy]["failure"] += 1

        # Update avg response time
        stats = self.strategy_stats[domain][strategy]
        total = stats["success"] + stats["failure"]
        current_avg = stats["avg_response_time"]
        stats["avg_response_time"] = (current_avg * (total - 1) + response_time_ms) / total

    def record_attempt(self, domain: str, strategy: Strategy, failure_class: FailureClass, response_time_ms: float):
        """
        Record crawl attempt outcome for ML feedback.

        Args:
            domain: Target domain
            strategy: Strategy used
            failure_class: Classification of the attempt result
            response_time_ms: Response time in milliseconds
        """
        success = (failure_class == FailureClass.SUCCESS)
        self.update(domain, strategy, success, response_time_ms)

    def recommend_strategies(self, failure_class: FailureClass) -> list[Strategy]:
        """
        Recommend strategies to try based on failure type.

        Args:
            failure_class: Type of failure encountered

        Returns:
            List of recommended strategies
        """
        recommendations = {
            FailureClass.RATE_LIMIT: [
                Strategy.EXTENDED_DELAYS,
                Strategy.PROXY_ROTATION,
                Strategy.COOKIE_PERSISTENCE,
            ],
            FailureClass.CAPTCHA: [
                Strategy.BROWSER_MODE,
                Strategy.EXTENDED_DELAYS,
                Strategy.PROXY_ROTATION,
            ],
            FailureClass.FINGERPRINT_DETECTED: [
                Strategy.TLS_FINGERPRINT_ROTATION,
                Strategy.HEADERS_VARIATION,
                Strategy.BROWSER_MODE,
            ],
            FailureClass.IP_BLOCKED: [
                Strategy.PROXY_ROTATION,
                Strategy.EXTENDED_DELAYS,
            ],
            FailureClass.TIMEOUT: [
                Strategy.EXTENDED_DELAYS,
                Strategy.PROXY_ROTATION,
            ],
            FailureClass.SERVER_ERROR: [
                Strategy.EXTENDED_DELAYS,
            ],
        }

        return recommendations.get(failure_class, [Strategy.TLS_FINGERPRINT_ROTATION])

    def _initialize_domain(self, domain: str):
        """Initialize strategy statistics for new domain."""
        self.strategy_stats[domain] = {
            strategy: {"success": 0, "failure": 0, "avg_response_time": 0.0}
            for strategy in Strategy
        }

    def get_domain_stats(self, domain: str) -> Dict:
        """
        Get statistics for a specific domain.

        Args:
            domain: Target domain

        Returns:
            Dict of {domain: {strategy: stats}}
        """
        if domain not in self.strategy_stats:
            return {}

        return {domain: self.strategy_stats[domain]}

    def _best_strategy(self, domain: str) -> Strategy:
        """
        Select strategy with highest success rate.

        Uses Upper Confidence Bound (UCB) for tie-breaking:
        - Prefers strategies with higher success rate
        - Adds exploration bonus for under-tried strategies
        """
        stats = self.strategy_stats[domain]

        # Calculate total attempts across all strategies
        total_attempts = sum(
            counts["success"] + counts["failure"]
            for counts in stats.values()
        )

        best_strategies = []
        best_score = -1

        for strategy, counts in stats.items():
            total = counts["success"] + counts["failure"]

            if total == 0:
                # Never tried: optimistic initialization, but reduce bonus as total attempts grow
                # This allows exploitation of known-good strategies after sufficient exploration
                exploration_factor = max(0.5, 1.0 - (total_attempts / 200))
                score = exploration_factor
            else:
                # Success rate + exploration bonus
                success_rate = counts["success"] / total
                exploration_bonus = ((1.0 / (total + 1)) ** 0.5) * 0.1  # Reduced UCB bonus
                score = success_rate + exploration_bonus

            if score > best_score:
                best_score = score
                best_strategies = [strategy]
            elif score == best_score:
                best_strategies.append(strategy)

        # If multiple strategies have same score, pick randomly
        return random.choice(best_strategies) if best_strategies else self.default_strategy

    def get_stats(self, domain: str | None = None) -> Dict:
        """
        Get strategy statistics for domain or all domains.

        Args:
            domain: Specific domain or None for all domains

        Returns:
            If domain specified: {strategy: {"success": int, "failure": int, "rate": float}}
            If domain=None: {domain: {strategy: stats}}
        """
        if domain is not None:
            # Return stats for specific domain
            if domain not in self.strategy_stats:
                return {}

            stats_with_rates = {}
            for strategy, counts in self.strategy_stats[domain].items():
                total = counts["success"] + counts["failure"]
                rate = counts["success"] / total if total > 0 else 0.0

                stats_with_rates[strategy] = {
                    "success": counts["success"],
                    "failure": counts["failure"],
                    "total": total,
                    "success_rate": rate
                }

            return stats_with_rates
        else:
            # Return all domains' stats
            return self.strategy_stats

    async def load_from_db(self):
        """Load historical statistics from feedback.db."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT domain, strategy, success_count, failure_count
                    FROM strategy_effectiveness
                """)

                rows = await cursor.fetchall()
                for domain, strategy_name, success, failure in rows:
                    if domain not in self.strategy_stats:
                        self._initialize_domain(domain)

                    try:
                        strategy = Strategy(strategy_name)
                        self.strategy_stats[domain][strategy] = {
                            "success": success,
                            "failure": failure
                        }
                    except ValueError:
                        # Unknown strategy in DB (skip)
                        continue

        except Exception as e:
            # DB doesn't exist yet or error reading
            pass

    async def save_to_db(self):
        """Persist statistics to feedback.db."""
        async with aiosqlite.connect(self.db_path) as db:
            for domain, strategies in self.strategy_stats.items():
                for strategy, counts in strategies.items():
                    await db.execute("""
                        INSERT INTO strategy_effectiveness
                        (domain, strategy, success_count, failure_count, last_updated)
                        VALUES (?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(domain, strategy) DO UPDATE SET
                            success_count = excluded.success_count,
                            failure_count = excluded.failure_count,
                            last_updated = datetime('now')
                    """, (domain, strategy.value, counts["success"], counts["failure"]))

            await db.commit()

    def get_domain_recommendation(self, domain: str) -> Dict[str, any]:
        """
        Get recommendation for domain.
        
        Returns:
            Dict with best strategy, confidence, and advice
        """
        if domain not in self.strategy_stats:
            return {
                "domain": domain,
                "status": "new",
                "recommendation": self.default_strategy.value,
                "confidence": 0.0,
                "advice": "No data yet - using default strategy"
            }

        best_strategy = self._best_strategy(domain)
        stats = self.get_stats(domain)
        best_stats = stats[best_strategy]

        # Calculate confidence
        total_attempts = sum(s["total"] for s in stats.values())
        confidence = min(1.0, total_attempts / 50)  # Confident after 50 attempts

        return {
            "domain": domain,
            "status": "learned",
            "recommendation": best_strategy.value,
            "success_rate": best_stats["success_rate"],
            "attempts": best_stats["total"],
            "confidence": confidence,
            "advice": self._generate_advice(best_stats)
        }

    def _generate_advice(self, stats: dict) -> str:
        """Generate human-readable advice based on stats."""
        rate = stats["success_rate"]
        total = stats["total"]

        if total < 10:
            return "Still learning - need more data"
        elif rate > 0.8:
            return "High success rate - strategy working well"
        elif rate > 0.5:
            return "Moderate success - may need adjustment"
        else:
            return "Low success rate - consider different approach"
