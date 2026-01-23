"""Rule-based failure classifier (MVP - no ML model yet).

Phase 1: Use heuristic rules to classify failures.
Phase 2: Train ML model (PyTorch/XGBoost) on labeled data.
"""

import re
from typing import Any

from .models import FailureClass


class FailureClassifier:
    """Classify crawl failures using heuristic rules.

    In Phase 2, this will be replaced with a trained ML model.
    """

    # Patterns indicating different failure types
    CAPTCHA_PATTERNS = [
        r"captcha",
        r"recaptcha",
        r"hcaptcha",
        r"cloudflare",
        r"access denied",
        r"challenge",
        r"bot detection",
        r"automated access",
    ]

    RATE_LIMIT_PATTERNS = [
        r"rate limit",
        r"too many requests",
        r"throttled",
        r"retry after",
        r"slow down",
    ]

    FINGERPRINT_PATTERNS = [
        r"suspicious activity",
        r"unusual behavior",
        r"automated",
        r"bot",
        r"blocked",
        r"access restricted",
    ]

    def __init__(self):
        """Initialize classifier."""
        self.captcha_regex = re.compile(
            "|".join(self.CAPTCHA_PATTERNS), re.IGNORECASE
        )
        self.rate_limit_regex = re.compile(
            "|".join(self.RATE_LIMIT_PATTERNS), re.IGNORECASE
        )
        self.fingerprint_regex = re.compile(
            "|".join(self.FINGERPRINT_PATTERNS), re.IGNORECASE
        )

    def classify(
        self,
        status_code: int,
        response_time_ms: float,
        response_body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> FailureClass:
        """Classify a crawl attempt.

        Args:
            status_code: HTTP status code (0 if no response)
            response_time_ms: Response time in milliseconds
            response_body: Response body text (optional)
            headers: Response headers (optional)

        Returns:
            Classified failure type
        """
        # Success
        if 200 <= status_code < 300:
            return FailureClass.SUCCESS

        # Timeout (no response or very slow)
        if status_code == 0 or response_time_ms > 30000:
            return FailureClass.TIMEOUT

        # Rate limiting
        if status_code == 429:
            return FailureClass.RATE_LIMIT

        # Check for rate limit in headers
        if headers:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            if retry_after:
                return FailureClass.RATE_LIMIT

        # Forbidden - likely blocking
        if status_code == 403:
            # Try to determine specific type from response body
            if response_body:
                if self.captcha_regex.search(response_body):
                    return FailureClass.CAPTCHA
                if self.fingerprint_regex.search(response_body):
                    return FailureClass.FINGERPRINT_DETECTED

            # Default to IP blocked for 403
            return FailureClass.IP_BLOCKED

        # CAPTCHA detection from response
        if response_body and self.captcha_regex.search(response_body):
            return FailureClass.CAPTCHA

        # Check for rate limiting in body
        if response_body and self.rate_limit_regex.search(response_body):
            return FailureClass.RATE_LIMIT

        # Server errors
        if 500 <= status_code < 600:
            return FailureClass.SERVER_ERROR

        # Slow response with success code (possible soft rate limiting)
        if 200 <= status_code < 300 and response_time_ms > 10000:
            return FailureClass.RATE_LIMIT

        # Unknown
        return FailureClass.UNKNOWN

    def extract_features(
        self,
        status_code: int,
        response_time_ms: float,
        response_size: int,
        headers: dict[str, str] | None = None,
        proxy_used: bool = False,
        hour_of_day: int = 0,
    ) -> dict[str, Any]:
        """Extract features for ML training (Phase 2).

        Args:
            status_code: HTTP status code
            response_time_ms: Response time
            response_size: Response body size
            headers: Response headers
            proxy_used: Whether proxy was used
            hour_of_day: Hour of day (0-23)

        Returns:
            Feature dictionary for ML model
        """
        features = {
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "response_size": response_size,
            "proxy_used": int(proxy_used),
            "hour_of_day": hour_of_day,
            "is_client_error": int(400 <= status_code < 500),
            "is_server_error": int(500 <= status_code < 600),
            "is_slow": int(response_time_ms > 5000),
            "is_very_slow": int(response_time_ms > 10000),
            "has_retry_after": 0,
            "response_size_category": self._categorize_size(response_size),
        }

        if headers:
            features["has_retry_after"] = int(
                "Retry-After" in headers or "retry-after" in headers
            )

        return features

    def _categorize_size(self, size: int) -> int:
        """Categorize response size into buckets.

        Args:
            size: Response size in bytes

        Returns:
            Size category (0-5)
        """
        if size == 0:
            return 0
        elif size < 1024:
            return 1
        elif size < 10240:
            return 2
        elif size < 102400:
            return 3
        elif size < 1048576:
            return 4
        else:
            return 5

    def should_retry(
        self,
        failure_class: FailureClass,
        attempt_number: int,
        max_retries: int = 3,
    ) -> bool:
        """Determine if request should be retried based on failure type.

        Args:
            failure_class: Classified failure type
            attempt_number: Current attempt number (1-indexed)
            max_retries: Maximum retry attempts

        Returns:
            Whether to retry
        """
        if attempt_number >= max_retries:
            return False

        # Always retry timeouts and server errors
        if failure_class in [FailureClass.TIMEOUT, FailureClass.SERVER_ERROR]:
            return True

        # Retry rate limits with backoff
        if failure_class == FailureClass.RATE_LIMIT:
            return True

        # Don't retry CAPTCHAs or fingerprint detection (need strategy change)
        if failure_class in [FailureClass.CAPTCHA, FailureClass.FINGERPRINT_DETECTED]:
            return False

        # Retry IP blocks (with different proxy)
        if failure_class == FailureClass.IP_BLOCKED:
            return True

        # Retry unknowns
        if failure_class == FailureClass.UNKNOWN:
            return attempt_number < 2

        return False

    def get_retry_delay_ms(
        self,
        failure_class: FailureClass,
        attempt_number: int,
    ) -> int:
        """Get recommended retry delay in milliseconds.

        Args:
            failure_class: Classified failure type
            attempt_number: Current attempt number

        Returns:
            Delay in milliseconds
        """
        base_delays = {
            FailureClass.TIMEOUT: 5000,
            FailureClass.RATE_LIMIT: 10000,
            FailureClass.SERVER_ERROR: 2000,
            FailureClass.IP_BLOCKED: 1000,
            FailureClass.UNKNOWN: 2000,
        }

        base = base_delays.get(failure_class, 1000)

        # Exponential backoff
        return base * (2 ** (attempt_number - 1))
