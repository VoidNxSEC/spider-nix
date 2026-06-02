"""
Failure Classifier - Rule-based classification of crawl failures.

Classifies why HTTP requests fail into 8 categories:
- SUCCESS
- RATE_LIMIT
- FINGERPRINT_DETECTED (bot detection)
- CAPTCHA
- IP_BLOCKED
- TIMEOUT
- SERVER_ERROR
- NETWORK_ERROR
- UNKNOWN

This enables adaptive strategy selection based on failure patterns.
"""

from dataclasses import dataclass
from typing import Any

from .models import FailureClass


class Evidence(dict[str, Any]):
    """Dict evidence with text-like helpers for older tests and callers."""

    def lower(self) -> str:
        return " ".join(str(value).lower() for value in self.values() if value is not None)


@dataclass
class ClassificationResult:
    """Result of failure classification."""

    failure_class: FailureClass
    confidence: float  # 0.0-1.0
    evidence: Evidence

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FailureClass):
            return self.failure_class == other
        return super().__eq__(other)


class FailureClassifier:
    """
    Rule-based failure classification (MVP).

    Uses heuristics to classify why requests fail:
    - Status code patterns
    - Response body keywords
    - Headers analysis
    - Exception types

    Future: Replace with ML classifier trained on feedback.db
    """

    def __init__(self):
        """Initialize classifier with detection patterns."""
        # CAPTCHA detection patterns
        self.captcha_indicators = [
            "recaptcha",
            "g-recaptcha",
            "hcaptcha",
            "h-captcha",
            "cloudflare challenge",
            "cf-challenge",
            "cf-chl-bypass",
            "verify you are human",
            "captcha",
            "bot detection",
            "security check",
        ]

        # Bot detection indicators
        self.bot_indicators = [
            "access denied",
            "blocked",
            "automated",
            "bot detected",
            "suspicious activity",
            "datadome",
            "perimeterx",
            "_px",
            "imperva",
        ]

        # Rate limit indicators
        self.rate_limit_indicators = [
            "rate limit",
            "too many requests",
            "quota exceeded",
            "throttled",
            "retry after",
        ]

        # WAF headers
        self.waf_headers = {
            "cloudflare": ["cf-ray", "cf-cache-status"],
            "akamai": ["akamai-grn"],
            "incapsula": ["x-cdn"],
            "aws-waf": ["x-amzn-requestid"],
        }

    def classify(
        self,
        status_code: int,
        response_headers: dict[str, str] | None = None,
        response_body: str | None = None,
        response_time_ms: float = 0.0,
        exception: Exception | None = None,
        headers: dict[str, str] | None = None,
    ) -> ClassificationResult:
        """
        Classify why request failed.

        Args:
            status_code: HTTP status code
            response_headers: Response headers dict (can be None)
            response_body: Response body text (can be None)
            response_time_ms: Response time in milliseconds
            exception: Exception raised (if any)

        Returns:
            ClassificationResult with failure class and confidence
        """
        # Handle None values
        response_headers = response_headers or headers or {}
        response_body = response_body or ""
        headers_lower = {k.lower(): v for k, v in response_headers.items()}
        body_lower = response_body.lower()

        # 1. Transport failures
        if exception and isinstance(exception, TimeoutError):
            return self._result(
                FailureClass.TIMEOUT,
                1.0,
                response_time_ms=response_time_ms,
                exception=str(exception),
                reason="timeout_exception",
            )

        if exception and isinstance(exception, (ConnectionError, OSError)):
            return self._result(
                FailureClass.NETWORK_ERROR,
                0.95,
                exception=str(exception),
                reason="connection_error",
            )

        if status_code == 0:
            return self._result(
                FailureClass.TIMEOUT,
                0.95,
                response_time_ms=response_time_ms,
                reason="no_response",
            )

        # 2. RATE_LIMIT
        retry_after = headers_lower.get("retry-after")
        matched_rate = next((ind for ind in self.rate_limit_indicators if ind in body_lower), None)
        if status_code == 429 or retry_after or matched_rate:
            return self._result(
                FailureClass.RATE_LIMIT,
                0.95,
                status_code=status_code,
                retry_after=retry_after,
                matched_indicator=matched_rate or "429",
                reason="rate_limit",
            )

        if 200 <= status_code < 300 and response_time_ms >= 10000:
            return self._result(
                FailureClass.RATE_LIMIT,
                0.75,
                status_code=status_code,
                response_time_ms=response_time_ms,
                reason="slow_success",
            )

        # 3. CAPTCHA
        if self._is_captcha(response_body, response_headers):
            provider = self._detect_captcha_provider(response_body, response_headers)
            return self._result(
                FailureClass.CAPTCHA,
                0.90,
                status_code=status_code,
                captcha_provider=provider,
                waf=self._detect_waf(response_headers),
                reason=f"{provider} captcha",
            )

        # 4. SUCCESS
        if 200 <= status_code < 300:
            # Check for soft blocks (200 but blocked content)
            if self._is_soft_block(response_body):
                return self._result(
                    FailureClass.FINGERPRINT_DETECTED,
                    0.85,
                    reason="soft_block_in_200",
                    body_length=len(response_body),
                )
            return self._result(FailureClass.SUCCESS, 1.0, status_code=status_code)

        # 4. IP_BLOCKED (check before FINGERPRINT_DETECTED for better priority)
        if status_code == 403 and ("ip" in body_lower and "block" in body_lower):
            return self._result(
                FailureClass.IP_BLOCKED,
                0.85,
                status_code=status_code,
                reason="ip_block_mentioned",
            )

        # 5. FINGERPRINT_DETECTED (bot detection)
        bot_indicator = next((ind for ind in self.bot_indicators if ind in body_lower), None)
        if bot_indicator or self._is_bot_challenge(response_body, response_headers):
            return self._result(
                FailureClass.FINGERPRINT_DETECTED,
                0.85,
                status_code=status_code,
                waf=self._detect_waf(response_headers),
                bot_indicator=bot_indicator,
                reason="bot or automated browser detected",
            )

        if status_code in [403, 401]:
            return self._result(
                FailureClass.IP_BLOCKED,
                0.70,
                status_code=status_code,
                reason="generic 403 ip blocked",
            )

        # 7. SERVER_ERROR
        if 500 <= status_code < 600:
            return self._result(
                FailureClass.SERVER_ERROR,
                0.95,
                status_code=status_code,
                reason="server_error",
            )

        # 9. UNKNOWN
        return self._result(
            FailureClass.UNKNOWN,
            0.5,
            status_code=status_code,
            reason="no_pattern_matched",
        )

    def _result(
        self, failure_class: FailureClass, confidence: float, **evidence: Any
    ) -> ClassificationResult:
        return ClassificationResult(failure_class, confidence, Evidence(evidence))

    def should_retry(
        self,
        failure_class: FailureClass,
        attempt_number: int,
        max_retries: int = 3,
    ) -> bool:
        if attempt_number >= max_retries:
            return False
        return failure_class in {
            FailureClass.TIMEOUT,
            FailureClass.NETWORK_ERROR,
            FailureClass.RATE_LIMIT,
            FailureClass.SERVER_ERROR,
            FailureClass.IP_BLOCKED,
            FailureClass.FINGERPRINT_DETECTED,
        }

    def get_retry_delay_ms(self, failure_class: FailureClass, attempt_number: int) -> int:
        base_delays: dict[FailureClass, int] = {
            FailureClass.RATE_LIMIT: 2000,
            FailureClass.SERVER_ERROR: 1000,
            FailureClass.TIMEOUT: 1500,
            FailureClass.NETWORK_ERROR: 1000,
            FailureClass.IP_BLOCKED: 3000,
            FailureClass.FINGERPRINT_DETECTED: 2500,
        }
        base = base_delays.get(failure_class, 1000)
        return int(base * (2 ** max(0, attempt_number - 1)))

    def extract_features(
        self,
        status_code: int,
        response_time_ms: float,
        response_size: int,
        proxy_used: bool,
        hour_of_day: int,
    ) -> dict[str, int | float]:
        return {
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "response_size": response_size,
            "proxy_used": 1 if proxy_used else 0,
            "hour_of_day": hour_of_day,
            "is_slow": 1 if response_time_ms > 5000 else 0,
            "is_client_error": 1 if 400 <= status_code < 500 else 0,
            "is_server_error": 1 if 500 <= status_code < 600 else 0,
        }

    def _is_captcha(self, body: str, headers: dict[str, str]) -> bool:
        """Detect CAPTCHA challenges."""
        body_lower = body.lower()
        server = headers.get("server", headers.get("Server", "")).lower()
        return any(indicator in body_lower for indicator in self.captcha_indicators) or (
            "cloudflare" in server and "cf-challenge" in body_lower
        )

    def _detect_captcha_provider(self, body: str, headers: dict[str, str] | None = None) -> str:
        """Identify CAPTCHA provider."""
        body_lower = body.lower()
        headers = headers or {}
        server = headers.get("server", headers.get("Server", "")).lower()
        if "recaptcha" in body_lower:
            return "recaptcha"
        elif "hcaptcha" in body_lower or "h-captcha" in body_lower:
            return "hcaptcha"
        elif "cloudflare" in body_lower or "cf-challenge" in body_lower or "cloudflare" in server:
            return "cloudflare"
        elif "funcaptcha" in body_lower or "arkose" in body_lower:
            return "funcaptcha"
        return "unknown"

    def _is_bot_challenge(self, body: str, headers: dict[str, str]) -> bool:
        """Detect bot challenges (Cloudflare, DataDome, PerimeterX)."""
        body_lower = body.lower()

        # Cloudflare
        if headers.get("Server") == "cloudflare" and "cf_clearance" in body_lower:
            return True

        # DataDome
        if "datadome" in body_lower:
            return True

        # PerimeterX
        if "_px" in body_lower or "perimeterx" in body_lower:
            return True

        # Generic bot block messages
        return any(ind in body_lower for ind in self.bot_indicators)

    def _is_soft_block(self, body: str) -> bool:
        """
        Detect soft blocks (200 status but blocked content).

        Indicators:
        - Suspiciously small response (<200 bytes) with block keywords
        - Generic error pages with block keywords
        """
        body_lower = body.lower()
        soft_block_indicators = [
            "access denied",
            "blocked",
            "forbidden",
            "not authorized",
            "access restricted",
        ]

        # Only treat as soft block if BOTH small AND has keywords
        # OR has strong block keywords regardless of size
        has_block_keyword = any(ind in body_lower for ind in soft_block_indicators)

        if len(body) < 200 and has_block_keyword:
            return True

        # Strong indicators even with normal size
        if "access denied" in body_lower or "access restricted" in body_lower:
            return True

        return False

    def _detect_waf(self, headers: dict[str, str]) -> str | None:
        """Detect Web Application Firewall."""
        headers_lower = {k.lower(): v for k, v in headers.items()}

        for waf, header_keys in self.waf_headers.items():
            if any(key in headers_lower for key in header_keys):
                return str(waf)

        return None
