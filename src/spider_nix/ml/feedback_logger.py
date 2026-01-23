"""Feedback logger for storing crawl attempts and learning."""

import aiosqlite
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import CrawlAttempt, FailureClass, Strategy, StrategyEffectiveness


class FeedbackLogger:
    """Log crawl attempts to database for ML training and analysis.

    Provides async interface for high-performance logging during crawls.
    """

    def __init__(self, db_path: str | Path = "feedback.db"):
        """Initialize feedback logger.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._initialized = False

    async def initialize(self):
        """Initialize database schema."""
        if self._initialized:
            return

        # Create database directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Load schema
        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text()

        # Execute schema
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(schema)
            await db.commit()

        self._initialized = True

    async def log_attempt(self, attempt: CrawlAttempt):
        """Log a crawl attempt.

        Args:
            attempt: Crawl attempt record
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO crawl_attempts (
                    url, domain, status_code, response_time_ms, response_size,
                    failure_class, strategies_used, proxy_used, tls_fingerprint,
                    timestamp, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.url,
                    attempt.domain,
                    attempt.status_code,
                    attempt.response_time_ms,
                    attempt.response_size,
                    attempt.failure_class.value,
                    json.dumps([s.value for s in attempt.strategies_used]),
                    attempt.proxy_used,
                    attempt.tls_fingerprint,
                    attempt.timestamp.isoformat(),
                    json.dumps(attempt.metadata),
                ),
            )
            await db.commit()

    async def update_strategy_effectiveness(
        self,
        domain: str,
        strategy: Strategy,
        success: bool,
        response_time_ms: float,
    ):
        """Update strategy effectiveness statistics.

        Args:
            domain: Target domain
            strategy: Strategy used
            success: Whether attempt succeeded
            response_time_ms: Response time
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            # Check if record exists
            cursor = await db.execute(
                """
                SELECT success_count, failure_count, avg_response_time_ms
                FROM strategy_effectiveness
                WHERE domain = ? AND strategy = ?
                """,
                (domain, strategy.value),
            )
            row = await cursor.fetchone()

            if row:
                # Update existing record
                success_count, failure_count, avg_time = row
                total = success_count + failure_count

                if success:
                    success_count += 1
                else:
                    failure_count += 1

                # Update rolling average
                new_avg = ((avg_time * total) + response_time_ms) / (total + 1)

                await db.execute(
                    """
                    UPDATE strategy_effectiveness
                    SET success_count = ?, failure_count = ?,
                        avg_response_time_ms = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE domain = ? AND strategy = ?
                    """,
                    (success_count, failure_count, new_avg, domain, strategy.value),
                )
            else:
                # Insert new record
                await db.execute(
                    """
                    INSERT INTO strategy_effectiveness (
                        domain, strategy, success_count, failure_count,
                        avg_response_time_ms
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        domain,
                        strategy.value,
                        1 if success else 0,
                        0 if success else 1,
                        response_time_ms,
                    ),
                )

            await db.commit()

    async def get_strategy_effectiveness(
        self, domain: str
    ) -> list[StrategyEffectiveness]:
        """Get strategy effectiveness for a domain.

        Args:
            domain: Target domain

        Returns:
            List of strategy effectiveness records
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT domain, strategy, success_count, failure_count,
                       avg_response_time_ms, last_updated
                FROM strategy_effectiveness
                WHERE domain = ?
                ORDER BY success_count DESC, avg_response_time_ms ASC
                """,
                (domain,),
            )

            results = []
            async for row in cursor:
                results.append(
                    StrategyEffectiveness(
                        domain=row[0],
                        strategy=Strategy(row[1]),
                        success_count=row[2],
                        failure_count=row[3],
                        avg_response_time_ms=row[4],
                    )
                )

            return results

    async def get_best_strategy(self, domain: str) -> Strategy | None:
        """Get best performing strategy for a domain.

        Args:
            domain: Target domain

        Returns:
            Best strategy or None if no data
        """
        effectiveness = await self.get_strategy_effectiveness(domain)

        if not effectiveness:
            return None

        # Sort by success rate, then by response time
        best = max(
            effectiveness,
            key=lambda e: (e.success_rate, -e.avg_response_time_ms),
        )

        return best.strategy if best.success_rate > 0 else None

    async def get_failure_distribution(self, domain: str | None = None) -> dict[str, int]:
        """Get distribution of failure classes.

        Args:
            domain: Optional domain filter

        Returns:
            Dict mapping failure class to count
        """
        await self.initialize()

        query = """
            SELECT failure_class, COUNT(*) as count
            FROM crawl_attempts
        """
        params: tuple[Any, ...] = ()

        if domain:
            query += " WHERE domain = ?"
            params = (domain,)

        query += " GROUP BY failure_class"

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            result = {}
            async for row in cursor:
                result[row[0]] = row[1]
            return result

    async def get_training_data(
        self, limit: int = 1000, min_timestamp: str | None = None
    ) -> list[dict[str, Any]]:
        """Get training data for ML classifier.

        Args:
            limit: Max number of records
            min_timestamp: Minimum timestamp filter (ISO format)

        Returns:
            List of training records as dicts
        """
        await self.initialize()

        query = "SELECT * FROM crawl_attempts"
        params: tuple[Any, ...] = ()

        if min_timestamp:
            query += " WHERE timestamp >= ?"
            params = (min_timestamp,)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params = (*params, limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)

            results = []
            async for row in cursor:
                results.append(dict(row))

            return results

    async def get_stats(self) -> dict[str, Any]:
        """Get overall statistics.

        Returns:
            Dictionary of statistics
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            # Total attempts
            cursor = await db.execute("SELECT COUNT(*) FROM crawl_attempts")
            total = (await cursor.fetchone())[0]

            # Success rate
            cursor = await db.execute(
                """
                SELECT COUNT(*) FROM crawl_attempts
                WHERE failure_class = 'success'
                """
            )
            successes = (await cursor.fetchone())[0]

            # Unique domains
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT domain) FROM crawl_attempts"
            )
            domains = (await cursor.fetchone())[0]

            # Average response time
            cursor = await db.execute(
                "SELECT AVG(response_time_ms) FROM crawl_attempts"
            )
            avg_time = (await cursor.fetchone())[0] or 0.0

            return {
                "total_attempts": total,
                "success_count": successes,
                "success_rate": successes / total if total > 0 else 0.0,
                "unique_domains": domains,
                "avg_response_time_ms": avg_time,
            }
