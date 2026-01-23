"""Advanced rate limiting, circuit breaker, and request deduplication."""

import asyncio
import hashlib
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class RateLimitStats:
    """Statistics for adaptive rate limiting."""
    requests_sent: int = 0
    requests_success: int = 0
    requests_blocked: int = 0
    requests_failed: int = 0
    avg_response_time_ms: float = 0.0
    current_delay_ms: float = 500.0
    backpressure_detected: bool = False


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open to close
    timeout_seconds: float = 60.0  # Time before half-open retry
    half_open_max_calls: int = 3  # Max calls in half-open state


class CircuitBreaker:
    """Circuit breaker pattern for handling cascading failures."""

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        async with self._lock:
            # Check if circuit is open
            if self.state == CircuitState.OPEN:
                # Check if timeout elapsed
                if time.monotonic() - self.last_failure_time >= self.config.timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    self.success_count = 0
                else:
                    raise CircuitBreakerError("Circuit breaker is OPEN")

            # Limit calls in half-open state
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerError("Circuit breaker half-open limit reached")
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise e

    async def _on_success(self):
        """Handle successful call."""
        async with self._lock:
            self.failure_count = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.half_open_calls = 0

    async def _on_failure(self):
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.half_open_calls = 0
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.state

    def reset(self):
        """Manually reset circuit breaker."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_calls = 0


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter with backpressure detection.

    Automatically adjusts request rate based on:
    - Response times (slow responses = reduce rate)
    - HTTP status codes (429, 503 = backpressure)
    - Error rates (high errors = slow down)
    """

    def __init__(
        self,
        initial_delay_ms: float = 500.0,
        min_delay_ms: float = 100.0,
        max_delay_ms: float = 5000.0,
        backpressure_threshold: float = 0.2,  # 20% error rate
        response_time_threshold_ms: float = 3000.0,
        adjustment_factor: float = 1.5,
        window_size: int = 100,
    ):
        self.initial_delay_ms = initial_delay_ms
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backpressure_threshold = backpressure_threshold
        self.response_time_threshold_ms = response_time_threshold_ms
        self.adjustment_factor = adjustment_factor
        self.window_size = window_size

        self.current_delay_ms = initial_delay_ms
        self.stats = RateLimitStats(current_delay_ms=initial_delay_ms)

        # Sliding windows for adaptive decision making
        self._response_times: deque[float] = deque(maxlen=window_size)
        self._status_codes: deque[int] = deque(maxlen=window_size)
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait before making next request (rate limit)."""
        await asyncio.sleep(self.current_delay_ms / 1000)

    async def report_request(
        self,
        status_code: int,
        response_time_ms: float,
        error: bool = False,
    ):
        """Report request result for adaptive rate adjustment."""
        async with self._lock:
            self.stats.requests_sent += 1

            if error:
                self.stats.requests_failed += 1
            elif status_code in {429, 503, 504}:
                self.stats.requests_blocked += 1
            elif 200 <= status_code < 300:
                self.stats.requests_success += 1

            self._response_times.append(response_time_ms)
            self._status_codes.append(status_code)

            # Update average response time
            if self._response_times:
                self.stats.avg_response_time_ms = sum(self._response_times) / len(self._response_times)

            # Detect backpressure
            await self._detect_backpressure()

            # Adjust rate
            await self._adjust_rate()

    async def _detect_backpressure(self):
        """Detect if server is under pressure."""
        if len(self._status_codes) < 10:
            return

        # Calculate error rate
        recent_codes = list(self._status_codes)[-20:]
        error_count = sum(1 for code in recent_codes if code in {429, 500, 502, 503, 504})
        error_rate = error_count / len(recent_codes)

        # Check response times
        recent_times = list(self._response_times)[-20:]
        avg_time = sum(recent_times) / len(recent_times)

        self.stats.backpressure_detected = (
            error_rate > self.backpressure_threshold or
            avg_time > self.response_time_threshold_ms
        )

    async def _adjust_rate(self):
        """Adjust request rate based on server response."""
        if not self._status_codes:
            return

        last_code = self._status_codes[-1]

        # Slow down on backpressure signals
        if last_code in {429, 503, 504}:
            self.current_delay_ms *= self.adjustment_factor
            self.current_delay_ms = min(self.current_delay_ms, self.max_delay_ms)

        # Slow down if average response time is high
        elif self.stats.avg_response_time_ms > self.response_time_threshold_ms:
            self.current_delay_ms *= 1.2
            self.current_delay_ms = min(self.current_delay_ms, self.max_delay_ms)

        # Speed up if everything is good
        elif 200 <= last_code < 300 and self.stats.avg_response_time_ms < 1000:
            self.current_delay_ms /= 1.1
            self.current_delay_ms = max(self.current_delay_ms, self.min_delay_ms)

        self.stats.current_delay_ms = self.current_delay_ms

    def get_stats(self) -> RateLimitStats:
        """Get current rate limiting statistics."""
        return self.stats

    def reset(self):
        """Reset rate limiter to initial state."""
        self.current_delay_ms = self.initial_delay_ms
        self.stats = RateLimitStats(current_delay_ms=self.initial_delay_ms)
        self._response_times.clear()
        self._status_codes.clear()


class RequestDeduplicator:
    """
    Deduplicate requests by normalizing URLs and content hashing.

    Features:
    - URL normalization (sorting query params, removing fragments)
    - Content-based deduplication (hash comparison)
    - Time-based expiry for cache
    """

    def __init__(
        self,
        max_cache_size: int = 10000,
        ttl_seconds: float = 3600.0,
    ):
        self.max_cache_size = max_cache_size
        self.ttl_seconds = ttl_seconds

        self._url_cache: dict[str, float] = {}  # url -> timestamp
        self._content_cache: dict[str, float] = {}  # content_hash -> timestamp
        self._lock = asyncio.Lock()

    def normalize_url(self, url: str) -> str:
        """
        Normalize URL for deduplication.

        - Sort query parameters
        - Remove fragments
        - Lowercase scheme and netloc
        - Remove default ports
        """
        parsed = urlparse(url)

        # Sort query parameters
        query_params = parse_qs(parsed.query)
        sorted_query = urlencode(sorted(query_params.items()), doseq=True)

        # Normalize scheme and netloc
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Remove default ports
        if netloc.endswith(":80") and scheme == "http":
            netloc = netloc[:-3]
        elif netloc.endswith(":443") and scheme == "https":
            netloc = netloc[:-4]

        # Reconstruct without fragment
        normalized = urlunparse((
            scheme,
            netloc,
            parsed.path or "/",
            parsed.params,
            sorted_query,
            "",  # No fragment
        ))

        return normalized

    def hash_content(self, content: str) -> str:
        """Generate hash of content for deduplication."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def is_duplicate_url(self, url: str) -> bool:
        """Check if URL has been seen recently."""
        normalized = self.normalize_url(url)

        async with self._lock:
            self._cleanup_expired()

            if normalized in self._url_cache:
                return True

            self._url_cache[normalized] = time.monotonic()

            # Prevent cache from growing too large
            if len(self._url_cache) > self.max_cache_size:
                # Remove oldest 10%
                sorted_items = sorted(self._url_cache.items(), key=lambda x: x[1])
                for url_to_remove, _ in sorted_items[:self.max_cache_size // 10]:
                    del self._url_cache[url_to_remove]

            return False

    async def is_duplicate_content(self, content: str) -> bool:
        """Check if content has been seen recently."""
        content_hash = self.hash_content(content)

        async with self._lock:
            self._cleanup_expired()

            if content_hash in self._content_cache:
                return True

            self._content_cache[content_hash] = time.monotonic()

            # Prevent cache from growing too large
            if len(self._content_cache) > self.max_cache_size:
                sorted_items = sorted(self._content_cache.items(), key=lambda x: x[1])
                for hash_to_remove, _ in sorted_items[:self.max_cache_size // 10]:
                    del self._content_cache[hash_to_remove]

            return False

    def _cleanup_expired(self):
        """Remove expired entries from cache."""
        current_time = time.monotonic()

        # Clean URL cache
        expired_urls = [
            url for url, timestamp in self._url_cache.items()
            if current_time - timestamp > self.ttl_seconds
        ]
        for url in expired_urls:
            del self._url_cache[url]

        # Clean content cache
        expired_content = [
            hash_val for hash_val, timestamp in self._content_cache.items()
            if current_time - timestamp > self.ttl_seconds
        ]
        for hash_val in expired_content:
            del self._content_cache[hash_val]

    def clear(self):
        """Clear all caches."""
        self._url_cache.clear()
        self._content_cache.clear()

    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        return {
            "url_cache_size": len(self._url_cache),
            "content_cache_size": len(self._content_cache),
            "total_cache_size": len(self._url_cache) + len(self._content_cache),
        }
