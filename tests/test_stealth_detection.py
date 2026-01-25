"""
Detection testing suite for stealth effectiveness validation.

Tests spider-nix stealth engine against common bot detection sites.
"""

import pytest
import asyncio
from pathlib import Path
from spider_nix.browser import BrowserCrawler
from spider_nix.config import CrawlerConfig
from spider_nix.stealth import StealthEngine


@pytest.fixture
async def crawler():
    """Create browser crawler with stealth enabled."""
    config = CrawlerConfig(
        timeout=30,
        user_agent_rotation=True,
        respect_robots_txt=False,
    )
    crawler = BrowserCrawler(config, proxy_rotator=None)
    yield crawler
    # Cleanup handled by crawler


class TestBotDetection:
    """Test anti-detection effectiveness against known bot detection sites."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_sannysoft_detection(self, crawler):
        """
        Test against Sannysoft Bot Detection test page.

        Expected: Zero red flags, all checks should appear human-like.
        """
        url = "https://bot.sannysoft.com"

        result = await crawler.crawl(
            url,
            max_pages=1,
            follow_links=False,
            screenshot=True
        )

        content = result[0].content if result else ""

        # Critical checks (MUST PASS)
        assert "WebDriver: false" in content or "webdriver: false" in content, \
            "WebDriver property not hidden"

        assert "Chrome: present" in content or "chrome: true" in content, \
            "Chrome object not present (bot indicator)"

        # Check for automation detection strings (MUST NOT BE PRESENT)
        bot_indicators = [
            "automation",
            "headless",
            "phantom",
            "selenium",
            "webdriver: true",
        ]

        for indicator in bot_indicators:
            assert indicator.lower() not in content.lower(), \
                f"Bot indicator found: {indicator}"

        # Permissions API check
        assert "Permissions: present" in content or "permissions" in content.lower(), \
            "Permissions API not spoofed correctly"

        print(f"✓ Sannysoft test PASSED - zero bot indicators detected")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_incolumitas_headless_detection(self, crawler):
        """
        Test against Incolumitas/Arh bot detection.

        Expected: Should NOT be detected as headless.
        """
        url = "https://arh.antoinevastel.com/bots/areyouheadless"

        result = await crawler.crawl(
            url,
            max_pages=1,
            follow_links=False,
            screenshot=True
        )

        content = result[0].content if result else ""

        # Key detection checks
        assert "You are not Chrome headless" in content or \
               "not headless" in content.lower(), \
               "Detected as headless Chrome"

        assert "automation" not in content.lower(), \
               "Automation detected"

        print(f"✓ Incolumitas test PASSED - not detected as headless")

    @pytest.mark.asyncio
    async def test_canvas_fingerprint_consistency(self, crawler):
        """
        Test canvas fingerprint noise injection.

        Expected: Canvas fingerprints should vary slightly between sessions
        due to noise, but be consistent within a session.
        """
        # Create simple HTML page with canvas fingerprinting
        canvas_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <canvas id="test" width="200" height="50"></canvas>
            <script>
                const canvas = document.getElementById('test');
                const ctx = canvas.getContext('2d');
                ctx.textBaseline = 'top';
                ctx.font = '14px Arial';
                ctx.fillText('Canvas fingerprint test', 2, 2);
                document.body.innerHTML += canvas.toDataURL();
            </script>
        </body>
        </html>
        """

        # Test 1: Within-session consistency
        # (Same browser instance should produce same fingerprint)
        page = await crawler._create_page()
        await page.set_content(canvas_html)
        fp1 = await page.content()
        await page.reload()
        fp2 = await page.content()

        # Should be identical within session
        assert fp1 == fp2, "Canvas fingerprint not consistent within session"

        await page.close()

        # Test 2: Cross-session variation
        # (Different sessions should produce different fingerprints due to noise)
        fingerprints = []
        for _ in range(3):
            # New crawler = new session = new noise seed
            config = CrawlerConfig()
            new_crawler = BrowserCrawler(config, proxy_rotator=None)
            page = await new_crawler._create_page()
            await page.set_content(canvas_html)
            fp = await page.content()
            fingerprints.append(fp)
            await page.close()

        # All should be unique (noise injection working)
        unique_fps = len(set(fingerprints))
        assert unique_fps == 3, \
            f"Canvas fingerprints not varying between sessions (only {unique_fps}/3 unique)"

        print(f"✓ Canvas fingerprint test PASSED - noise injection working")

    @pytest.mark.asyncio
    async def test_webgl_fingerprint(self, crawler):
        """
        Test WebGL fingerprint randomization.

        Expected: WebGL vendor/renderer should be from our pool.
        """
        webgl_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <canvas id="glcanvas"></canvas>
            <script>
                const canvas = document.getElementById('glcanvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');

                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                const vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
                const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);

                document.body.innerHTML = `
                    <div id="vendor">${vendor}</div>
                    <div id="renderer">${renderer}</div>
                `;
            </script>
        </body>
        </html>
        """

        page = await crawler._create_page()
        await page.set_content(webgl_html)

        vendor = await page.locator("#vendor").text_content()
        renderer = await page.locator("#renderer").text_content()

        await page.close()

        # Verify vendor is from our pool
        from spider_nix.stealth import WEBGL_VENDORS
        valid_vendors = [v for v, _ in WEBGL_VENDORS]

        assert vendor in valid_vendors, \
            f"WebGL vendor '{vendor}' not in expected pool"

        # Verify renderer looks realistic
        assert any(keyword in renderer for keyword in ["ANGLE", "NVIDIA", "AMD", "Intel", "Apple"]), \
            f"WebGL renderer '{renderer}' doesn't look realistic"

        print(f"✓ WebGL fingerprint test PASSED - {vendor} / {renderer}")

    @pytest.mark.asyncio
    async def test_cdp_markers_cleanup(self, crawler):
        """
        Test Chrome DevTools Protocol (CDP) markers are cleaned up.

        Expected: No CDP markers should be present in window object.
        """
        cdp_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <script>
                const markers = [
                    'cdc_adoQpoasnfa76pfcZLmcfl_Array',
                    'cdc_adoQpoasnfa76pfcZLmcfl_Promise',
                    'cdc_adoQpoasnfa76pfcZLmcfl_Symbol',
                    '$cdc_asdjflasutopfhvcZLmcfl_',
                    '$chrome_asyncScriptInfo'
                ];

                const found = markers.filter(m => window[m] !== undefined);
                document.body.innerHTML = `<div id="result">${found.join(',') || 'CLEAN'}</div>`;
            </script>
        </body>
        </html>
        """

        page = await crawler._create_page()
        await page.set_content(cdp_html)

        result = await page.locator("#result").text_content()
        await page.close()

        assert result == "CLEAN", \
            f"CDP markers found: {result}"

        print(f"✓ CDP markers cleanup test PASSED")

    @pytest.mark.asyncio
    async def test_battery_api_blocked(self, crawler):
        """
        Test Battery API is blocked (fingerprinting vector).

        Expected: getBattery() should be undefined or rejected.
        """
        battery_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <script>
                (async () => {
                    let status = 'BLOCKED';

                    if (navigator.getBattery === undefined) {
                        status = 'UNDEFINED';
                    } else {
                        try {
                            await navigator.getBattery();
                            status = 'EXPOSED';  // BAD!
                        } catch(e) {
                            status = 'REJECTED';  // GOOD!
                        }
                    }

                    document.body.innerHTML = `<div id="result">${status}</div>`;
                })();
            </script>
        </body>
        </html>
        """

        page = await crawler._create_page()
        await page.set_content(battery_html)

        # Wait for async script to complete
        await asyncio.sleep(0.5)

        result = await page.locator("#result").text_content()
        await page.close()

        assert result in ["UNDEFINED", "REJECTED", "BLOCKED"], \
            f"Battery API not properly blocked: {result}"

        print(f"✓ Battery API blocking test PASSED - status: {result}")

    @pytest.mark.asyncio
    async def test_plugins_array_empty(self, crawler):
        """
        Test plugins array is spoofed as empty (modern browsers).

        Expected: navigator.plugins should be empty array.
        """
        plugins_html = """
        <!DOCTYPE html>
        <html>
        <body>
            <script>
                const count = navigator.plugins.length;
                document.body.innerHTML = `<div id="result">${count}</div>`;
            </script>
        </body>
        </html>
        """

        page = await crawler._create_page()
        await page.set_content(plugins_html)

        result = await page.locator("#result").text_content()
        await page.close()

        assert result == "0", \
            f"Plugins array not empty: {result} plugins found"

        print(f"✓ Plugins array spoofing test PASSED - 0 plugins")


class TestFingerprintRealism:
    """Test fingerprint values are within realistic distributions."""

    def test_stealth_engine_fingerprint_generation(self):
        """Test fingerprint generation produces realistic values."""
        engine = StealthEngine()

        # Generate multiple fingerprints
        for _ in range(10):
            fp = engine.get_fingerprint()

            # Screen resolution checks
            assert fp["screen"]["width"] >= 1280, "Screen width too small"
            assert fp["screen"]["height"] >= 720, "Screen height too small"
            assert fp["screen"]["colorDepth"] in [24, 30], "Invalid color depth"
            assert 1.0 <= fp["screen"]["pixelRatio"] <= 2.0, "Invalid pixel ratio"

            # Hardware checks
            assert fp["hardwareConcurrency"] in [4, 8, 12, 16, 20, 24], \
                "Invalid CPU core count"
            assert fp["deviceMemory"] in [4, 8, 16, 32, 64], \
                "Invalid device memory"

            # Platform checks
            assert fp["platform"] in ["Win32", "Linux x86_64", "MacIntel"], \
                "Invalid platform"

            # WebGL checks
            assert fp["webgl"]["vendor"], "WebGL vendor missing"
            assert fp["webgl"]["renderer"], "WebGL renderer missing"

            # Correlation checks (MacBook should have Apple GPU)
            if fp["platform"] == "MacIntel":
                assert "Apple" in fp["webgl"]["vendor"] or "Intel" in fp["webgl"]["vendor"], \
                    f"Mac platform has non-Mac GPU: {fp['webgl']['vendor']}"
                assert fp["screen"]["pixelRatio"] == 2.0, \
                    "Mac should have Retina display (2.0 pixel ratio)"

        print(f"✓ Fingerprint realism test PASSED - 10 samples verified")

    def test_noise_generation_variation(self):
        """Test noise factors vary between sessions."""
        noises = []

        for _ in range(5):
            engine = StealthEngine()
            noises.append((engine._canvas_noise, engine._audio_noise))

        # All should be unique
        unique_noises = len(set(noises))
        assert unique_noises == 5, \
            f"Noise not varying between sessions (only {unique_noises}/5 unique)"

        # Verify ranges
        for canvas_noise, audio_noise in noises:
            assert 0.00001 <= canvas_noise <= 0.0001, \
                f"Canvas noise out of range: {canvas_noise}"
            assert 0.000001 <= audio_noise <= 0.00002, \
                f"Audio noise out of range: {audio_noise}"

        print(f"✓ Noise variation test PASSED - 5 unique sessions")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
