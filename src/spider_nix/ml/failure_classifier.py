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

from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass


class FailureClass(str, Enum):
    """Failure classification types."""
    SUCCESS = "success"
    RATE_LIMIT = "rate_limit"
    FINGERPRINT_DETECTED = "fingerprint_detected"
    CAPTCHA = "captcha"
    IP_BLOCKED = "ip_blocked"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of failure classification."""
    failure_class: FailureClass
    confidence: float  # 0.0-1.0
    evidence: Dict[str, any]


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
            "recaptcha", "hcaptcha", "cloudflare challenge",
            "verify you are human", "captcha", "cf-chl-bypass",
            "bot detection", "security check"
        ]
        
        # Bot detection indicators
        self.bot_indicators = [
            "access denied", "blocked", "automated",
            "bot detected", "suspicious activity",
            "datadome", "perimeterx", "_px", "imperva"
        ]
        
        # Rate limit indicators
        self.rate_limit_indicators = [
            "rate limit", "too many requests",
            "quota exceeded", "throttled",
            "retry after"
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
        response_headers: Optional[Dict[str, str]],
        response_body: Optional[str],
        response_time_ms: float,
        exception: Optional[Exception] = None
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
        response_headers = response_headers or {}
        response_body = response_body or ""
        body_lower = response_body.lower()
        
        # 1. SUCCESS
        if 200 <= status_code < 300:
            # Check for soft blocks (200 but blocked content)
            if self._is_soft_block(response_body):
                return ClassificationResult(
                    failure_class=FailureClass.FINGERPRINT_DETECTED,
                    confidence=0.85,
                    evidence={"reason": "soft_block_in_200", "body_length": len(response_body)}
                )
            return ClassificationResult(
                failure_class=FailureClass.SUCCESS,
                confidence=1.0,
                evidence={"status_code": status_code}
            )

        # 2. RATE_LIMIT
        if status_code == 429 or any(ind in body_lower for ind in self.rate_limit_indicators):
            return ClassificationResult(
                failure_class=FailureClass.RATE_LIMIT,
                confidence=0.95,
                evidence={
                    "status_code": status_code,
                    "retry_after": response_headers.get("Retry-After"),
                    "matched_indicator": next((ind for ind in self.rate_limit_indicators if ind in body_lower), None)
                }
            )

        # 3. CAPTCHA
        if self._is_captcha(response_body, response_headers):
            return ClassificationResult(
                failure_class=FailureClass.CAPTCHA,
                confidence=0.90,
                evidence={
                    "status_code": status_code,
                    "captcha_provider": self._detect_captcha_provider(response_body),
                    "waf": self._detect_waf(response_headers)
                }
            )

        # 4. IP_BLOCKED (check before FINGERPRINT_DETECTED for better priority)
        if status_code == 403 and ("ip" in body_lower and "block" in body_lower):
            return ClassificationResult(
                failure_class=FailureClass.IP_BLOCKED,
                confidence=0.85,
                evidence={"status_code": status_code, "reason": "ip_block_mentioned"}
            )

        # 5. FINGERPRINT_DETECTED (bot detection)
        if status_code in [403, 401] or self._is_bot_challenge(response_body, response_headers):
            return ClassificationResult(
                failure_class=FailureClass.FINGERPRINT_DETECTED,
                confidence=0.85,
                evidence={
                    "status_code": status_code,
                    "waf": self._detect_waf(response_headers),
                    "bot_indicator": next((ind for ind in self.bot_indicators if ind in body_lower), None)
                }
            )

        # 6. TIMEOUT
        if exception and isinstance(exception, TimeoutError):
            return ClassificationResult(
                failure_class=FailureClass.TIMEOUT,
                confidence=1.0,
                evidence={"response_time_ms": response_time_ms, "exception": str(exception)}
            )

        # 7. SERVER_ERROR
        if 500 <= status_code < 600:
            return ClassificationResult(
                failure_class=FailureClass.SERVER_ERROR,
                confidence=0.95,
                evidence={"status_code": status_code}
            )

        # 8. NETWORK_ERROR
        if exception and isinstance(exception, (ConnectionError, OSError)):
            return ClassificationResult(
                failure_class=FailureClass.NETWORK_ERROR,
                confidence=0.95,
                evidence={"exception": str(exception)}
            )

        # 9. UNKNOWN
        return ClassificationResult(
            failure_class=FailureClass.UNKNOWN,
            confidence=0.5,
            evidence={"status_code": status_code, "reason": "no_pattern_matched"}
        )

    def _is_captcha(self, body: str, headers: Dict[str, str]) -> bool:
        """Detect CAPTCHA challenges."""
        body_lower = body.lower()
        return any(indicator in body_lower for indicator in self.captcha_indicators)

    def _detect_captcha_provider(self, body: str) -> str:
        """Identify CAPTCHA provider."""
        body_lower = body.lower()
        if "recaptcha" in body_lower:
            return "recaptcha"
        elif "hcaptcha" in body_lower:
            return "hcaptcha"
        elif "cloudflare" in body_lower:
            return "cloudflare"
        elif "funcaptcha" in body_lower or "arkose" in body_lower:
            return "funcaptcha"
        return "unknown"

    def _is_bot_challenge(self, body: str, headers: Dict[str, str]) -> bool:
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
            "access denied", "blocked", "forbidden",
            "not authorized", "access restricted"
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

    def _detect_waf(self, headers: Dict[str, str]) -> Optional[str]:
        """Detect Web Application Firewall."""
        headers_lower = {k.lower(): v for k, v in headers.items()}
        
        for waf, header_keys in self.waf_headers.items():
            if any(key in headers_lower for key in header_keys):
                return waf

        return None
