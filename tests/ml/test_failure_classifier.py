"""Tests for failure classifier."""

import pytest
from spider_nix.ml.failure_classifier import FailureClassifier
from spider_nix.ml.models import FailureClass


class TestFailureClassifier:
    """Test failure classification."""

    def test_classify_success(self):
        """Test successful request classification."""
        classifier = FailureClassifier()

        result = classifier.classify(status_code=200, response_time_ms=500)
        assert result == FailureClass.SUCCESS

    def test_classify_timeout(self):
        """Test timeout classification."""
        classifier = FailureClassifier()

        # No response
        result = classifier.classify(status_code=0, response_time_ms=0)
        assert result == FailureClass.TIMEOUT

        # Very slow response
        result = classifier.classify(status_code=0, response_time_ms=35000)
        assert result == FailureClass.TIMEOUT

    def test_classify_rate_limit(self):
        """Test rate limiting classification."""
        classifier = FailureClassifier()

        # 429 status
        result = classifier.classify(status_code=429, response_time_ms=100)
        assert result == FailureClass.RATE_LIMIT

        # Retry-After header
        result = classifier.classify(
            status_code=403,
            response_time_ms=100,
            headers={"Retry-After": "60"},
        )
        assert result == FailureClass.RATE_LIMIT

        # Slow success (soft rate limit)
        result = classifier.classify(status_code=200, response_time_ms=15000)
        assert result == FailureClass.RATE_LIMIT

    def test_classify_captcha(self):
        """Test CAPTCHA detection."""
        classifier = FailureClassifier()

        result = classifier.classify(
            status_code=403,
            response_time_ms=500,
            response_body="Please complete the reCAPTCHA challenge",
        )
        assert result == FailureClass.CAPTCHA

        result = classifier.classify(
            status_code=200,
            response_time_ms=500,
            response_body="<div class='h-captcha'>Verify you are human</div>",
        )
        assert result == FailureClass.CAPTCHA

    def test_classify_ip_blocked(self):
        """Test IP blocking detection."""
        classifier = FailureClassifier()

        # 403 without specific patterns defaults to IP blocked
        result = classifier.classify(status_code=403, response_time_ms=100)
        assert result == FailureClass.IP_BLOCKED

    def test_classify_server_error(self):
        """Test server error classification."""
        classifier = FailureClassifier()

        for code in [500, 502, 503, 504]:
            result = classifier.classify(status_code=code, response_time_ms=100)
            assert result == FailureClass.SERVER_ERROR

    def test_should_retry(self):
        """Test retry decision logic."""
        classifier = FailureClassifier()

        # Always retry timeouts
        assert classifier.should_retry(FailureClass.TIMEOUT, attempt_number=1)
        assert classifier.should_retry(FailureClass.TIMEOUT, attempt_number=2)

        # Don't retry CAPTCHAs
        assert not classifier.should_retry(FailureClass.CAPTCHA, attempt_number=1)

        # Don't retry if max attempts reached
        assert not classifier.should_retry(FailureClass.TIMEOUT, attempt_number=3, max_retries=3)

    def test_get_retry_delay(self):
        """Test retry delay calculation."""
        classifier = FailureClassifier()

        # Exponential backoff
        delay1 = classifier.get_retry_delay_ms(FailureClass.RATE_LIMIT, attempt_number=1)
        delay2 = classifier.get_retry_delay_ms(FailureClass.RATE_LIMIT, attempt_number=2)
        delay3 = classifier.get_retry_delay_ms(FailureClass.RATE_LIMIT, attempt_number=3)

        assert delay1 < delay2 < delay3

    def test_extract_features(self):
        """Test feature extraction for ML."""
        classifier = FailureClassifier()

        features = classifier.extract_features(
            status_code=429,
            response_time_ms=5500,
            response_size=1024,
            proxy_used=True,
            hour_of_day=14,
        )

        assert features["status_code"] == 429
        assert features["response_time_ms"] == 5500
        assert features["response_size"] == 1024
        assert features["proxy_used"] == 1
        assert features["hour_of_day"] == 14
        assert features["is_slow"] == 1  # > 5000ms
        assert features["is_client_error"] == 1  # 429 is 4xx
