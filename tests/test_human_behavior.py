"""
Real Playwright tests for human_behavior.py.

All tests launch a real headless Chromium — no mocks.
Uses page.set_content() so no network is needed.
"""

import asyncio
import pytest
from playwright.async_api import async_playwright

from spider_nix.intel.human_behavior import (
    human_move_to,
    human_scroll,
    human_type,
)

FORM_HTML = """
<!DOCTYPE html>
<html>
<body>
  <input id="name"  type="text"  placeholder="Full name" />
  <input id="email" type="email" placeholder="Email" />
  <textarea id="bio"></textarea>
  <div id="box" style="width:200px;height:50px;background:#eee;margin-top:100px"></div>
  <div id="log" style="height:2000px"></div>
</body>
</html>
"""


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def browser():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest.fixture
async def page(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    pg = await ctx.new_page()
    await pg.set_content(FORM_HTML)
    yield pg
    await pg.close()
    await ctx.close()


# ── human_type ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_type_basic_text(page):
    """Typed text must appear verbatim in the field."""
    await human_type(page, "#name", "Marcos Pina", wpm=120, typo_rate=0.0)
    value = await page.input_value("#name")
    assert value == "Marcos Pina"


@pytest.mark.asyncio
async def test_human_type_email_with_at_pause(page):
    """Email address must be typed correctly including the @ symbol."""
    await human_type(page, "#email", "marcos@voidnxlabs.io",
                     wpm=100, typo_rate=0.0, pause_after_at=True)
    value = await page.input_value("#email")
    assert value == "marcos@voidnxlabs.io"


@pytest.mark.asyncio
async def test_human_type_with_typos_still_correct(page):
    """With typo simulation enabled the final value must still be correct."""
    text = "security architect"
    # High typo rate to exercise correction path
    await human_type(page, "#name", text, wpm=80, typo_rate=0.3)
    value = await page.input_value("#name")
    assert value == text


@pytest.mark.asyncio
async def test_human_type_textarea(page):
    """human_type must work on textarea elements."""
    msg = "Cover letter paragraph."
    await human_type(page, "#bio", msg, wpm=90, typo_rate=0.0)
    value = await page.input_value("#bio")
    assert value == msg


@pytest.mark.asyncio
async def test_human_type_timing_is_nonzero(page):
    """Typing should not be instantaneous — must take measurable time."""
    import time
    text = "Hello"
    t0 = time.monotonic()
    await human_type(page, "#name", text, wpm=60, typo_rate=0.0)
    elapsed = time.monotonic() - t0
    # At 60 WPM, 5 chars ≈ 200ms. Floor at 50ms to avoid flake on fast CI.
    assert elapsed > 0.05, f"Typing completed unrealistically fast: {elapsed:.3f}s"


# ── human_move_to ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_move_to_element_handle(page):
    """Mouse must end up near the target element bounding box."""
    el = await page.query_selector("#box")
    assert el is not None
    await human_move_to(page, el, overshoot=False)

    pos = await page.evaluate("() => ({ x: window._lastMouseX, y: window._lastMouseY })")
    box = await el.bounding_box()

    # Final position must be within the element bounds (plus small tolerance)
    tol = 20
    assert box["x"] - tol <= pos["x"] <= box["x"] + box["width"] + tol
    assert box["y"] - tol <= pos["y"] <= box["y"] + box["height"] + tol


@pytest.mark.asyncio
async def test_human_move_to_css_selector(page):
    """human_move_to must accept a CSS selector string."""
    await human_move_to(page, "#name", overshoot=False)
    pos = await page.evaluate("() => ({ x: window._lastMouseX, y: window._lastMouseY })")
    # Just check that something moved (coordinates are not both zero/None)
    assert pos.get("x") is not None
    assert pos.get("y") is not None


@pytest.mark.asyncio
async def test_human_move_to_with_overshoot(page):
    """Overshoot=True must still land near the target after correction."""
    el = await page.query_selector("#box")
    await human_move_to(page, el, overshoot=True)

    pos = await page.evaluate("() => ({ x: window._lastMouseX, y: window._lastMouseY })")
    box = await el.bounding_box()

    tol = 30  # slightly larger tolerance for overshoot correction jitter
    assert box["x"] - tol <= pos["x"] <= box["x"] + box["width"] + tol
    assert box["y"] - tol <= pos["y"] <= box["y"] + box["height"] + tol


@pytest.mark.asyncio
async def test_human_move_to_missing_element_does_not_raise(page):
    """Moving to a non-existent element must silently no-op."""
    await human_move_to(page, "#does-not-exist")  # should not raise


# ── human_scroll ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_human_scroll_down_moves_page(page):
    """Scrolling down must increase window.scrollY."""
    before = await page.evaluate("() => window.scrollY")
    await human_scroll(page, direction="down", distance_px=300)
    after = await page.evaluate("() => window.scrollY")
    assert after > before, f"scrollY did not increase: {before} → {after}"


@pytest.mark.asyncio
async def test_human_scroll_up_after_down(page):
    """Scrolling up after down must decrease scrollY."""
    await human_scroll(page, direction="down", distance_px=400)
    mid = await page.evaluate("() => window.scrollY")
    await human_scroll(page, direction="up", distance_px=200)
    after = await page.evaluate("() => window.scrollY")
    assert after < mid, f"scrollY did not decrease: {mid} → {after}"
