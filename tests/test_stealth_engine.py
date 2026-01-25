"""Unit tests for StealthEngine (Phase 1A OPSEC)."""

import pytest
from spider_nix.stealth import StealthEngine


class TestFingerprintGeneration:
    """Test fingerprint generation produces realistic values."""

    def test_screen_resolution_realistic(self):
        """Test screen resolutions are within expected ranges."""
        engine = StealthEngine()

        for _ in range(10):
            fp = engine.get_fingerprint()
            screen = fp["screen"]

            # Should be common resolutions (≥ 1280x720)
            assert screen["width"] >= 1280, "Screen width too small"
            assert screen["height"] >= 720, "Screen height too small"

            # Color depth should be realistic
            assert screen["colorDepth"] in [24, 30, 32], f"Invalid color depth: {screen['colorDepth']}"

            # Pixel ratio should be realistic (1.0, 1.5, 2.0)
            assert 1.0 <= screen["pixelRatio"] <= 2.0, f"Invalid pixel ratio: {screen['pixelRatio']}"

    def test_hardware_concurrency_realistic(self):
        """Test CPU core counts are realistic."""
        engine = StealthEngine()

        for _ in range(10):
            fp = engine.get_fingerprint()

            # Common core counts: 4, 8, 12, 16, 20, 24
            assert fp["hardwareConcurrency"] in [4, 6, 8, 10, 12, 16, 20, 24], \
                f"Invalid core count: {fp['hardwareConcurrency']}"

    def test_device_memory_realistic(self):
        """Test device memory values are realistic."""
        engine = StealthEngine()

        for _ in range(10):
            fp = engine.get_fingerprint()

            # Common memory sizes: 4, 8, 16, 32, 64 GB
            assert fp["deviceMemory"] in [4, 8, 16, 32, 64], \
                f"Invalid device memory: {fp['deviceMemory']}"

    def test_platform_valid(self):
        """Test platform strings are valid."""
        engine = StealthEngine()

        valid_platforms = ["Win32", "Linux x86_64", "MacIntel"]

        for _ in range(10):
            fp = engine.get_fingerprint()
            assert fp["platform"] in valid_platforms, \
                f"Invalid platform: {fp['platform']}"

    def test_webgl_vendor_renderer_present(self):
        """Test WebGL vendor and renderer are present."""
        engine = StealthEngine()

        for _ in range(10):
            fp = engine.get_fingerprint()
            webgl = fp["webgl"]

            assert webgl["vendor"], "WebGL vendor missing"
            assert webgl["renderer"], "WebGL renderer missing"

            # Should contain realistic GPU brands
            vendor_lower = webgl["vendor"].lower()
            renderer_lower = webgl["renderer"].lower()

            assert any(brand in vendor_lower or brand in renderer_lower
                       for brand in ["nvidia", "amd", "intel", "apple", "google"]), \
                f"Unrealistic GPU: {webgl['vendor']} / {webgl['renderer']}"


class TestPlatformCorrelation:
    """Test platform-specific correlations (e.g., Mac → Apple GPU)."""

    def test_macos_has_apple_or_intel_gpu(self):
        """MacIntel should have Apple Silicon or Intel GPU."""
        engine = StealthEngine()

        for _ in range(20):
            fp = engine.get_fingerprint()

            if fp["platform"] == "MacIntel":
                vendor = fp["webgl"]["vendor"]
                renderer = fp["webgl"]["renderer"]

                # MacBook should have Apple or Intel GPU
                assert "Apple" in vendor or "Intel" in vendor or "AMD" in vendor, \
                    f"Mac has non-Mac GPU: {vendor}"

                # MacBook with Retina display should have 2.0 pixel ratio
                if "M1" in renderer or "M2" in renderer or "M3" in renderer:
                    assert fp["screen"]["pixelRatio"] == 2.0, \
                        "Apple Silicon Mac should have Retina display (2.0 ratio)"


class TestNoiseInjection:
    """Test per-session noise consistency."""

    def test_canvas_noise_per_session_consistent(self):
        """Canvas noise should be consistent within a session."""
        engine = StealthEngine()

        # Get noise factor (should be same for all calls in this session)
        noise1 = engine._canvas_noise
        noise2 = engine._canvas_noise

        assert noise1 == noise2, "Canvas noise should be consistent within session"
        assert 0.00001 <= noise1 <= 0.0001, f"Canvas noise out of range: {noise1}"

    def test_audio_noise_per_session_consistent(self):
        """Audio noise should be consistent within a session."""
        engine = StealthEngine()

        noise1 = engine._audio_noise
        noise2 = engine._audio_noise

        assert noise1 == noise2, "Audio noise should be consistent within session"
        assert 0.000001 <= noise1 <= 0.00002, f"Audio noise out of range: {noise1}"

    def test_noise_varies_between_sessions(self):
        """Noise should vary between different engine instances (sessions)."""
        noises = []

        for _ in range(5):
            engine = StealthEngine()
            noises.append((engine._canvas_noise, engine._audio_noise))

        # All should be unique
        unique_noises = len(set(noises))
        assert unique_noises == 5, \
            f"Noise not varying between sessions (only {unique_noises}/5 unique)"


class TestUserAgent:
    """Test user agent randomization."""

    def test_user_agent_realistic(self):
        """User agents should look realistic."""
        engine = StealthEngine()

        for _ in range(10):
            ua = engine.get_user_agent()

            # Should contain browser indicators
            assert any(browser in ua for browser in ["Chrome", "Firefox", "Edge", "Safari"]), \
                f"User agent doesn't contain browser: {ua}"

            # Should contain OS indicators
            assert any(os in ua for os in ["Windows", "Macintosh", "X11", "Linux"]), \
                f"User agent doesn't contain OS: {ua}"


class TestFingerprintDiversity:
    """Test fingerprint diversity across multiple generations."""

    def test_fingerprints_vary(self):
        """Multiple fingerprint generations should produce diverse results."""
        engine = StealthEngine()

        fingerprints = [engine.get_fingerprint() for _ in range(10)]

        # Extract key attributes
        screen_resolutions = set((fp["screen"]["width"], fp["screen"]["height"]) for fp in fingerprints)
        webgl_vendors = set(fp["webgl"]["vendor"] for fp in fingerprints)
        platforms = set(fp["platform"] for fp in fingerprints)

        # Should have diversity (at least 3 different values for each)
        assert len(screen_resolutions) >= 3, \
            f"Screen resolutions not diverse enough: {len(screen_resolutions)}/10"
        assert len(webgl_vendors) >= 2, \
            f"WebGL vendors not diverse enough: {len(webgl_vendors)}/10"
        assert len(platforms) >= 2, \
            f"Platforms not diverse enough: {len(platforms)}/10"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
