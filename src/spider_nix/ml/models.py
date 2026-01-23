"""Data models for ML feedback system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class FailureClass(str, Enum):
    """Classification of crawl failures."""
    SUCCESS = "success"
    RATE_LIMIT = "rate_limit"
    FINGERPRINT_DETECTED = "fingerprint_detected"
    CAPTCHA = "captcha"
    IP_BLOCKED = "ip_blocked"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class Strategy(str, Enum):
    """Available evasion strategies."""
    TLS_FINGERPRINT_ROTATION = "tls_fingerprint_rotation"
    PROXY_ROTATION = "proxy_rotation"
    BROWSER_MODE = "browser_mode"
    EXTENDED_DELAYS = "extended_delays"
    HEADERS_VARIATION = "headers_variation"
    COOKIE_PERSISTENCE = "cookie_persistence"


@dataclass
class CrawlAttempt:
    """Record of a single crawl attempt for ML feedback.

    Attributes:
        url: Target URL
        domain: Extracted domain
        status_code: HTTP status code (0 if failed before response)
        response_time_ms: Response time in milliseconds
        response_size: Response body size in bytes
        failure_class: Classified failure type
        strategies_used: List of strategies applied
        proxy_used: Proxy URL if used
        tls_fingerprint: TLS fingerprint identifier
        timestamp: When attempt was made
        metadata: Additional context
    """
    url: str
    domain: str
    status_code: int
    response_time_ms: float
    response_size: int
    failure_class: FailureClass
    strategies_used: list[Strategy]
    proxy_used: str | None = None
    tls_fingerprint: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        """Check if attempt was successful."""
        return self.failure_class == FailureClass.SUCCESS

    @property
    def is_blocked(self) -> bool:
        """Check if attempt was blocked (anti-bot detection)."""
        return self.failure_class in [
            FailureClass.RATE_LIMIT,
            FailureClass.FINGERPRINT_DETECTED,
            FailureClass.CAPTCHA,
            FailureClass.IP_BLOCKED,
        ]


@dataclass
class StrategyEffectiveness:
    """Tracks effectiveness of a strategy for a specific domain.

    Attributes:
        domain: Target domain
        strategy: Strategy identifier
        success_count: Number of successful attempts
        failure_count: Number of failed attempts
        avg_response_time_ms: Average response time
        last_updated: Last update timestamp
    """
    domain: str
    strategy: Strategy
    success_count: int = 0
    failure_count: int = 0
    avg_response_time_ms: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def total_attempts(self) -> int:
        """Total number of attempts."""
        return self.success_count + self.failure_count

    def update(self, success: bool, response_time_ms: float):
        """Update statistics with new attempt result.

        Args:
            success: Whether attempt succeeded
            response_time_ms: Response time in milliseconds
        """
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update rolling average response time
        total = self.total_attempts
        self.avg_response_time_ms = (
            (self.avg_response_time_ms * (total - 1) + response_time_ms) / total
        )
        self.last_updated = datetime.utcnow()
