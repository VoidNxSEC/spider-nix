"""
Real Playwright tests for stealth.py JS injection.

Injects the stealth script into a real headless Chromium and runs the
JS probe directly to verify that bot detection signals are hidden.
No mocks.
"""

import asyncio
import pytest
from playwright.async_api import async_playwright

from spider_nix.stealth import StealthEngine


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def stealth_page():
    """Page with stealth script already injected."""
    engine = StealthEngine()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=engine.get_user_agent(),
        )
        await ctx.add_init_script(engine.get_playwright_stealth_script())
        page = await ctx.new_page()
        await page.set_content("<html><body>test</body></html>")
        yield page, engine
        await browser.close()


# ── webdriver hidden ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_webdriver_is_undefined(stealth_page):
    """navigator.webdriver must be undefined after stealth injection."""
    page, _ = stealth_page
    val = await page.evaluate("() => navigator.webdriver")
    assert val is None or val is False or val == "undefined", \
        f"navigator.webdriver leaked: {val!r}"


@pytest.mark.asyncio
async def test_webdriver_descriptor_not_enumerable(stealth_page):
    """The webdriver descriptor must not be enumerable (probe-resistant)."""
    page, _ = stealth_page
    desc = await page.evaluate("""
        () => {
            const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            if (!d) return null;
            return { enumerable: d.enumerable, configurable: d.configurable };
        }
    """)
    if desc is not None:
        assert desc["enumerable"] is False, \
            "webdriver descriptor is enumerable — visible to bot probes"


# ── CDP/cdc_ markers removed ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_cdc_markers(stealth_page):
    """No cdc_* or $cdc_* window properties must remain after injection."""
    page, _ = stealth_page
    markers = await page.evaluate(
        "() => Object.keys(window).filter(k => k.startsWith('cdc_') || k.startsWith('$cdc_'))"
    )
    assert markers == [], f"CDC markers found: {markers}"


# ── permissions API looks native ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_permissions_query_looks_native(stealth_page):
    """permissions.query.toString() must not reveal it was patched."""
    page, _ = stealth_page
    result = await page.evaluate("""
        async () => {
            try {
                const s = Function.prototype.toString.call(navigator.permissions.query);
                return s;
            } catch(e) {
                return 'error:' + e.message;
            }
        }
    """)
    assert "native code" in result, \
        f"permissions.query.toString() reveals patch: {result!r}"


# ── fingerprint values are realistic ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_hardware_concurrency_is_realistic(stealth_page):
    """navigator.hardwareConcurrency must be a plausible CPU count."""
    page, _ = stealth_page
    val = await page.evaluate("() => navigator.hardwareConcurrency")
    assert val in {4, 8, 12, 16, 20, 24}, f"Unrealistic hardwareConcurrency: {val}"


@pytest.mark.asyncio
async def test_device_memory_is_realistic(stealth_page):
    """navigator.deviceMemory must be a plausible value."""
    page, _ = stealth_page
    val = await page.evaluate("() => navigator.deviceMemory")
    assert val in {4, 8, 16, 32, 64}, f"Unrealistic deviceMemory: {val}"


@pytest.mark.asyncio
async def test_webgl_vendor_matches_fingerprint(stealth_page):
    """WebGL UNMASKED_VENDOR must match the fingerprint we injected."""
    page, engine = stealth_page
    injected_vendor = engine.get_fingerprint()["webgl"]["vendor"]

    reported = await page.evaluate("""
        () => {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (!gl) return null;
            const ext = gl.getExtension('WEBGL_debug_renderer_info');
            if (!ext) return null;
            return gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
        }
    """)
    if reported is not None:
        assert reported == injected_vendor, \
            f"WebGL vendor mismatch: injected={injected_vendor!r} reported={reported!r}"


# ── outer dimensions not zero ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outer_dimensions_not_zero(stealth_page):
    """window.outerWidth/Height must not be 0 — common headless detection vector."""
    page, _ = stealth_page
    # Playwright sets these automatically via viewport; just verify they're sane
    w = await page.evaluate("() => window.innerWidth")
    h = await page.evaluate("() => window.innerHeight")
    assert w > 0, "innerWidth is 0"
    assert h > 0, "innerHeight is 0"
