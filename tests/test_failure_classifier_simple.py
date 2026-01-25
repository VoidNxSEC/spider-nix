"""Simplified unit tests for Failure Classifier (Phase 1D ML)."""

import pytest
from spider_nix.ml import FailureClassifier, FailureClass


class TestFailureClassifierCore:
    """Core tests for failure classification."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_success_200(self):
        """Test success detection (200 with valid content)."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={"content-type": "text/html"},
            response_body="<html><body>Page content here that is long enough</body></html>",
            response_time_ms=150.0
        )

        assert result.failure_class == FailureClass.SUCCESS
        assert result.confidence >= 0.9
        assert isinstance(result.evidence, dict)

    def test_rate_limit_429(self):
        """Test rate limit detection (429 status)."""
        result = self.classifier.classify(
            status_code=429,
            response_headers={"retry-after": "60"},
            response_body="Too Many Requests",
            response_time_ms=50.0
        )

        assert result.failure_class == FailureClass.RATE_LIMIT
        assert result.confidence >= 0.9
        assert result.evidence["status_code"] == 429

    def test_rate_limit_keywords(self):
        """Test rate limit detection via keywords."""
        result = self.classifier.classify(
            status_code=503,
            response_headers={},
            response_body="Rate limit exceeded. Please try again later.",
            response_time_ms=100.0
        )

        assert result.failure_class == FailureClass.RATE_LIMIT

    def test_captcha_recaptcha(self):
        """Test CAPTCHA detection (reCAPTCHA)."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body='<html><div class="g-recaptcha"></div></html>',
            response_time_ms=200.0
        )

        assert result.failure_class == FailureClass.CAPTCHA
        assert result.confidence >= 0.85
        assert result.evidence["captcha_provider"] in ["recaptcha", "unknown"]

    def test_captcha_hcaptcha(self):
        """Test CAPTCHA detection (hCaptcha)."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body='<html><div class="h-captcha" data-sitekey="xxx"></div></html>',
            response_time_ms=200.0
        )

        assert result.failure_class == FailureClass.CAPTCHA
        assert result.evidence["captcha_provider"] == "hcaptcha"

    def test_fingerprint_detected_403(self):
        """Test bot fingerprint detection (403)."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Access denied. Automated browser detected.",
            response_time_ms=80.0
        )

        assert result.failure_class == FailureClass.FINGERPRINT_DETECTED
        assert result.confidence >= 0.8

    def test_ip_blocked(self):
        """Test IP blocking detection."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Your IP address has been blocked.",
            response_time_ms=50.0
        )

        assert result.failure_class == FailureClass.IP_BLOCKED
        assert result.confidence >= 0.8
        assert result.evidence["reason"] == "ip_block_mentioned"

    def test_timeout_exception(self):
        """Test timeout exception handling."""
        result = self.classifier.classify(
            status_code=0,
            response_headers={},
            response_body="",
            response_time_ms=30000.0,
            exception=TimeoutError("Connection timed out")
        )

        assert result.failure_class == FailureClass.TIMEOUT
        assert result.confidence >= 0.95

    def test_server_error_500(self):
        """Test server error detection (500-599)."""
        result = self.classifier.classify(
            status_code=500,
            response_headers={},
            response_body="Internal Server Error",
            response_time_ms=200.0
        )

        assert result.failure_class == FailureClass.SERVER_ERROR
        assert result.confidence >= 0.9

    def test_server_error_502(self):
        """Test 502 Bad Gateway."""
        result = self.classifier.classify(
            status_code=502,
            response_headers={},
            response_body="Bad Gateway",
            response_time_ms=100.0
        )

        assert result.failure_class == FailureClass.SERVER_ERROR

    def test_network_error_connection(self):
        """Test network connection errors."""
        result = self.classifier.classify(
            status_code=0,
            response_headers={},
            response_body="",
            response_time_ms=0.0,
            exception=ConnectionError("Connection refused")
        )

        assert result.failure_class == FailureClass.NETWORK_ERROR
        assert result.confidence >= 0.9


class TestEdgeCases:
    """Test edge cases and None handling."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_none_body_handling(self):
        """Test handling of None response body."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={},
            response_body=None,
            response_time_ms=50.0
        )

        # Should handle gracefully
        assert isinstance(result.failure_class, FailureClass)
        assert result.confidence > 0

    def test_none_headers_handling(self):
        """Test handling of None headers."""
        result = self.classifier.classify(
            status_code=200,
            response_headers=None,
            response_body="Success content here",
            response_time_ms=50.0
        )

        # Should handle gracefully
        assert result.failure_class == FailureClass.SUCCESS

    def test_empty_body(self):
        """Test empty response body."""
        result = self.classifier.classify(
            status_code=200,
            response_headers={},
            response_body="",
            response_time_ms=50.0
        )

        # Empty body might be soft block or success
        assert result.failure_class in [FailureClass.SUCCESS, FailureClass.FINGERPRINT_DETECTED]


class TestPriorityOrder:
    """Test classification priority order."""

    def setup_method(self):
        """Setup classifier for each test."""
        self.classifier = FailureClassifier()

    def test_rate_limit_priority_over_server_error(self):
        """Rate limit keywords should override 503 status."""
        result = self.classifier.classify(
            status_code=503,
            response_headers={},
            response_body="Service temporarily unavailable. Rate limit exceeded.",
            response_time_ms=100.0
        )

        assert result.failure_class == FailureClass.RATE_LIMIT

    def test_captcha_priority_over_403(self):
        """CAPTCHA should be detected even with 403 status."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Please solve the CAPTCHA to continue. reCAPTCHA.",
            response_time_ms=200.0
        )

        assert result.failure_class == FailureClass.CAPTCHA

    def test_ip_block_priority_over_fingerprint(self):
        """IP block should be detected before fingerprint detection."""
        result = self.classifier.classify(
            status_code=403,
            response_headers={},
            response_body="Your IP has been blocked due to suspicious activity.",
            response_time_ms=50.0
        )

        assert result.failure_class == FailureClass.IP_BLOCKED


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
