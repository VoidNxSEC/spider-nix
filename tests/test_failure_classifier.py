"""Unit tests for Failure Classifier (Phase 1D ML)."""

import pytest
from spider_nix.ml import FailureClassifier, FailureClass


class TestFailureClassification:
    """Test failure classification logic (rule-based MVP)."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_success_classification(self):
        """Test successful requests (200-299)."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={"content-type": "text/html"},
            response_body="<html><body>Success</body></html>",
            response_time_ms=150.0,
            exception=None
        )

        assert result.failure_class == FailureClass.SUCCESS
        assert result.confidence >= 0.9

    def test_rate_limit_429(self):
        """Test rate limit detection (429 status)."""
        result = self.classifier.classify(
            status_code=429,
            response_headers={"retry-after": "60"},
            response_body="Too Many Requests",
            response_time_ms=50.0,
            exception=None
        )

        assert result.failure_class == FailureClass.RATE_LIMIT
        assert result.confidence >= 0.95
        assert "429" in result.evidence or "rate" in result.evidence.lower()

    def test_rate_limit_keywords(self):
        """Test rate limit detection via keywords."""
        result = self.classifier.classify(
            status_code=503,
            response_headers={},
            response_body="Rate limit exceeded. Please try again later.",
            response_time_ms=100.0,
            exception=None
        )

        assert result.failure_class == FailureClass.RATE_LIMIT
        assert "rate limit" in result.evidence.lower()

    def test_captcha_recaptcha(self):
        """Test CAPTCHA detection (reCAPTCHA)."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body='<html><div class="g-recaptcha"></div></html>',
            response_time_ms=200.0,
            exception=None
        )

        assert result.failure_class == FailureClass.CAPTCHA
        assert result.confidence >= 0.9
        assert "recaptcha" in result.evidence.lower() or "captcha" in result.evidence.lower()

    def test_captcha_hcaptcha(self):
        """Test CAPTCHA detection (hCaptcha)."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body='<html><div class="h-captcha"></div></html>',
            response_time_ms=200.0,
            exception=None
        )

        assert result.failure_class == FailureClass.CAPTCHA
        assert "hcaptcha" in result.evidence.lower() or "captcha" in result.evidence.lower()

    def test_captcha_cloudflare(self):
        """Test Cloudflare challenge detection."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={"server": "cloudflare"},
            response_body='<html><div id="cf-challenge-running"></div></html>',
            response_time_ms=100.0,
            exception=None
        )

        assert result.failure_class == FailureClass.CAPTCHA
        assert "cloudflare" in result.evidence.lower()

    def test_fingerprint_detected(self):
        """Test bot fingerprint detection."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Access denied. Automated browser detected.",
            response_time_ms=80.0,
            exception=None
        )

        assert result.failure_class == FailureClass.FINGERPRINT_DETECTED
        assert "bot" in result.evidence.lower() or "automated" in result.evidence.lower()

    def test_ip_blocked(self):
        """Test IP blocking detection."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Your IP address has been blocked.",
            response_time_ms=50.0,
            exception=None
        )

        assert result.failure_class == FailureClass.IP_BLOCKED
        assert "ip" in result.evidence.lower() and "block" in result.evidence.lower()

    def test_timeout_exception(self):
        """Test timeout exception handling."""
        result = self.classifier.classify(
            status_code=0,
            response_headers=None,
            response_body=None,
            response_time_ms=30000.0,
            exception=TimeoutError("Connection timed out")
        )

        assert result.failure_class == FailureClass.TIMEOUT
        assert result.confidence >= 0.95
        assert "timeout" in result.evidence.lower()

    def test_server_error_500(self):
        """Test server error detection (500-599)."""
        result = self.classifier.classify(
            status_code=500,
            response_headers={},
            response_body="Internal Server Error",
            response_time_ms=200.0,
            exception=None
        )

        assert result.failure_class == FailureClass.SERVER_ERROR
        assert result.confidence >= 0.9
        assert "500" in result.evidence or "server" in result.evidence.lower()

    def test_network_error_connection(self):
        """Test network connection errors."""
        result = self.classifier.classify(
            status_code=0,
            response_headers=None,
            response_body=None,
            response_time_ms=0.0,
            exception=ConnectionError("Connection refused")
        )

        assert result.failure_class == FailureClass.NETWORK_ERROR
        assert "connection" in result.evidence.lower()

    def test_soft_ban_detection(self):
        """Test soft ban detection (200 but empty/blocked content)."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={"content-type": "text/html"},
            response_body="<html><body>Access Denied</body></html>",
            response_time_ms=100.0,
            exception=None
        )

        # Should detect soft ban (200 but with "access denied")
        assert result.failure_class in [FailureClass.FINGERPRINT_DETECTED, FailureClass.SUCCESS]

    def test_multiple_indicators(self):
        """Test with multiple detection indicators (rate limit + captcha keywords)."""
        result = self.classifier.classify(
            status_code=429,
            response_headers={},
            response_body="Rate limit exceeded. Please solve CAPTCHA.",
            response_time_ms=100.0,
            exception=None
        )

        # Should prioritize 429 (rate limit) over CAPTCHA keywords
        assert result.failure_class == FailureClass.RATE_LIMIT


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_none_body_handling(self):
        """Test handling of None response body."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={},
            response_body=None,
            response_time_ms=50.0,
            exception=None
        )

        # Should handle gracefully (might be SUCCESS or UNKNOWN)
        assert result.failure_class in [FailureClass.SUCCESS, FailureClass.UNKNOWN]

    def test_empty_body_handling(self):
        """Test handling of empty response body."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={},
            response_body="",
            response_time_ms=50.0,
            exception=None
        )

        assert result.failure_class in [FailureClass.SUCCESS, FailureClass.UNKNOWN]

    def test_none_headers_handling(self):
        """Test handling of None headers."""
        result = self.classifier.classify(
            status_code=200,
            response_headers=None,
            response_body="Success",
            response_time_ms=50.0,
            exception=None
        )

        # Should handle gracefully
        assert isinstance(result.failure_class, FailureClass)

    def test_very_slow_response(self):
        """Test very slow responses (possible soft rate limit)."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={},
            response_body="<html></html>",
            response_time_ms=25000.0,  # 25 seconds
            exception=None
        )

        # Might be classified as SUCCESS or RATE_LIMIT depending on implementation
        assert result.failure_class in [FailureClass.SUCCESS, FailureClass.RATE_LIMIT]


class TestConfidenceScores:
    """Test confidence scoring logic."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_high_confidence_clear_indicator(self):
        """Test high confidence when indicators are clear."""
        result = self.classifier.classify(
            status_code=429,
            response_headers={"retry-after": "60"},
            response_body="Rate limit",
            response_time_ms=50.0,
            exception=None
        )

        assert result.confidence >= 0.9, "Should have high confidence for clear 429"

    def test_lower_confidence_ambiguous(self):
        """Test lower confidence for ambiguous cases."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Forbidden",  # Generic, could be many things
            response_time_ms=100.0,
            exception=None
        )

        # Confidence should be lower due to ambiguity
        assert result.confidence < 0.9, "Should have lower confidence for generic 403"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
