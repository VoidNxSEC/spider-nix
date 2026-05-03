"""
Real Playwright tests for block_logger.py.

Uses page.route() to inject synthetic 403/429 responses — real browser,
no network dependency.
"""

import asyncio
import json
import pytest
from pathlib import Path
from playwright.async_api import async_playwright

from spider_nix.intel.block_logger import BlockLogger, BLOCK_STATUSES


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
    ctx = await browser.new_context()
    pg = await ctx.new_page()
    yield pg
    await pg.close()
    await ctx.close()


# ── blocked response detection ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_block_logger_detects_403(page):
    """BlockLogger must detect a 403 and populate latest telemetry."""
    await page.route(
        "**/target",
        lambda route: route.fulfill(
            status=403,
            headers={"content-type": "text/html", "cf-ray": "abc123"},
            body="<html><body>Access Denied</body></html>",
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto("http://localhost/target")
        await asyncio.sleep(0.2)  # let the async capture complete

    assert bl.was_blocked
    t = bl.latest
    assert t.status == 403
    assert "access denied" in t.response_body_snippet.lower()


@pytest.mark.asyncio
async def test_block_logger_detects_429(page):
    """BlockLogger must detect a 429 rate-limit response."""
    await page.route(
        "**/rate",
        lambda route: route.fulfill(
            status=429,
            headers={"content-type": "application/json", "retry-after": "60"},
            body='{"error": "Too Many Requests"}',
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto("http://localhost/rate")
        await asyncio.sleep(0.2)

    assert bl.was_blocked
    assert bl.latest.status == 429


@pytest.mark.asyncio
async def test_block_logger_vendor_from_header(page):
    """antibot_vendor must be populated when a known vendor header is present."""
    await page.route(
        "**/blocked",
        lambda route: route.fulfill(
            status=403,
            headers={"content-type": "text/html", "x-datadome": "check"},
            body="blocked",
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto("http://localhost/blocked")
        await asyncio.sleep(0.2)

    assert bl.latest.antibot_vendor == "x-datadome"


@pytest.mark.asyncio
async def test_block_logger_no_block_on_200(page):
    """BlockLogger must NOT flag 200 OK as blocked."""
    await page.route(
        "**/ok",
        lambda route: route.fulfill(
            status=200,
            body="<html>OK</html>",
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto("http://localhost/ok")
        await asyncio.sleep(0.1)

    assert not bl.was_blocked


@pytest.mark.asyncio
async def test_block_logger_captures_console_errors(page):
    """Console errors from the page must appear in the telemetry."""
    await page.route(
        "**/errpage",
        lambda route: route.fulfill(
            status=403,
            body="<html><script>console.error('bot detected');</script></html>",
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto("http://localhost/errpage")
        await asyncio.sleep(0.3)

    t = bl.latest
    assert t is not None
    assert any("bot detected" in e for e in t.console_errors)


@pytest.mark.asyncio
async def test_block_logger_captures_network_log(page):
    """Network log must contain the blocked URL."""
    target_url = "http://localhost/netlog"
    await page.route(
        "**/netlog",
        lambda route: route.fulfill(
            status=403,
            body="blocked",
        ),
    )

    async with BlockLogger(page) as bl:
        await page.goto(target_url)
        await asyncio.sleep(0.2)

    t = bl.latest
    assert t is not None
    assert any("netlog" in entry["url"] for entry in t.network_log)


@pytest.mark.asyncio
async def test_block_logger_persists_json(page, tmp_path):
    """BlockLogger must write a JSON file when log_dir is provided."""
    await page.route(
        "**/save",
        lambda route: route.fulfill(
            status=403,
            body="forbidden",
        ),
    )

    async with BlockLogger(page, log_dir=tmp_path) as bl:
        await page.goto("http://localhost/save")
        await asyncio.sleep(0.3)

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text())
    assert data["status"] == 403
    assert "url" in data
    assert "response_headers" in data


# ── BLOCK_STATUSES coverage ───────────────────────────────────────────────────


def test_block_statuses_set():
    """BLOCK_STATUSES must include the canonical anti-bot codes."""
    assert 403 in BLOCK_STATUSES
    assert 429 in BLOCK_STATUSES
    assert 200 not in BLOCK_STATUSES
    assert 404 not in BLOCK_STATUSES  # 404 is content missing, not a block
