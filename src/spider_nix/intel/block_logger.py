"""
Blocked-request telemetry capture.

When a job board or ATS returns 4xx/challenge, capture everything needed
to diagnose which anti-bot layer triggered: headers, body, screenshot,
JS console errors, network waterfall, TLS timing.
"""

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Page, Request, Response

logger = logging.getLogger(__name__)

# HTTP status codes considered "blocked" (not normal 4xx like 404)
BLOCK_STATUSES = {400, 401, 403, 407, 429, 503, 511}

# Response header keys that identify anti-bot vendors
ANTIBOT_HEADER_KEYS = {
    "cf-ray",           # Cloudflare
    "x-datadome",       # DataDome
    "x-px-uuid",        # PerimeterX
    "x-recaptcha",      # reCAPTCHA
    "x-akamai-edgescape",
    "x-kasada-status",
}


@dataclass
class BlockTelemetry:
    url: str
    status: int
    response_headers: dict[str, str]
    response_body_snippet: str          # first 500 chars
    screenshot_b64: str | None          # PNG as base64, or None if unavailable
    console_errors: list[str]
    network_log: list[dict[str, Any]]   # requests fired before block
    timing: dict[str, float]            # tls_handshake_ms, ttfb_ms, dom_ready_ms
    antibot_vendor: str | None          # detected vendor if any
    js_detection_signals: dict[str, Any] = field(default_factory=dict)


class BlockLogger:
    """
    Attach to a Playwright Page and record blocked responses.

    Usage:
        async with BlockLogger(page, log_dir=Path("logs/blocks")) as bl:
            await page.goto(url)
            if bl.was_blocked:
                report = bl.latest
    """

    # JS probe injected to check what bot signals are leaking
    _PROBE_SCRIPT = """
    () => ({
        webdriver: navigator.webdriver,
        webdriverDescriptor: (() => {
            const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
            return d ? { enumerable: d.enumerable, configurable: d.configurable } : null;
        })(),
        permissionsQueryToString: navigator.permissions && navigator.permissions.query
            ? Function.prototype.toString.call(navigator.permissions.query)
            : null,
        plugins: navigator.plugins ? navigator.plugins.length : -1,
        chromeObject: typeof window.chrome !== 'undefined',
        cdcMarkers: Object.keys(window).filter(k => k.startsWith('cdc_') || k.startsWith('$cdc_')),
        outerWidthZero: window.outerWidth === 0,
        outerHeightZero: window.outerHeight === 0,
    })
    """

    def __init__(self, page: Page, log_dir: Path | None = None):
        self._page = page
        self._log_dir = log_dir
        self._console_errors: list[str] = []
        self._network_log: list[dict[str, Any]] = []
        self._page_start_ts: float = 0.0
        self._dom_ready_ts: float | None = None
        self._latest: BlockTelemetry | None = None

    @property
    def was_blocked(self) -> bool:
        return self._latest is not None

    @property
    def latest(self) -> BlockTelemetry | None:
        return self._latest

    async def __aenter__(self) -> "BlockLogger":
        self._page_start_ts = time.monotonic()
        self._page.on("console", self._on_console)
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)
        self._page.on("domcontentloaded", self._on_dom_ready)
        return self

    async def __aexit__(self, *_: Any) -> None:
        try:
            self._page.remove_listener("console", self._on_console)
            self._page.remove_listener("request", self._on_request)
            self._page.remove_listener("response", self._on_response)
            self._page.remove_listener("domcontentloaded", self._on_dom_ready)
        except Exception:
            pass

    def _on_console(self, msg: Any) -> None:
        if msg.type in ("error", "warning"):
            self._console_errors.append(f"[{msg.type}] {msg.text}")

    def _on_request(self, req: Request) -> None:
        self._network_log.append({
            "url": req.url,
            "method": req.method,
            "resource_type": req.resource_type,
            "ts_offset_ms": round((time.monotonic() - self._page_start_ts) * 1000, 1),
        })

    def _on_dom_ready(self) -> None:
        self._dom_ready_ts = time.monotonic()

    def _on_response(self, resp: Response) -> None:
        # Fire-and-forget async capture for blocked responses
        if resp.status in BLOCK_STATUSES:
            asyncio.ensure_future(self._capture(resp))

    async def _capture(self, resp: Response) -> None:
        headers = dict(resp.headers)
        vendor = next(
            (k for k in ANTIBOT_HEADER_KEYS if k in headers),
            None,
        )

        try:
            body_bytes = await resp.body()
            body_snippet = body_bytes.decode("utf-8", errors="replace")[:500]
        except Exception:
            body_snippet = "<body unavailable>"

        # Screenshot
        screenshot_b64: str | None = None
        try:
            png = await self._page.screenshot(type="png", full_page=False)
            screenshot_b64 = base64.b64encode(png).decode()
        except Exception:
            pass

        # Timing
        dom_ready_ms = (
            round((self._dom_ready_ts - self._page_start_ts) * 1000, 1)
            if self._dom_ready_ts
            else -1.0
        )
        timing: dict[str, float] = {
            "ttfb_ms": round(
                resp.request.timing.get("responseStart", 0)
                - resp.request.timing.get("requestStart", 0),
                1,
            ) if hasattr(resp.request, "timing") else -1.0,
            "dom_ready_ms": dom_ready_ms,
        }

        # JS probe (only if page is same-origin / not cross-origin error page)
        js_signals: dict[str, Any] = {}
        try:
            js_signals = await self._page.evaluate(self._PROBE_SCRIPT)
        except Exception:
            pass

        telemetry = BlockTelemetry(
            url=resp.url,
            status=resp.status,
            response_headers=headers,
            response_body_snippet=body_snippet,
            screenshot_b64=screenshot_b64,
            console_errors=list(self._console_errors),
            network_log=list(self._network_log),
            timing=timing,
            antibot_vendor=vendor,
            js_detection_signals=js_signals,
        )
        self._latest = telemetry
        self._persist(telemetry)

        # Log summary for immediate visibility
        cdc = js_signals.get("cdcMarkers", [])
        wd = js_signals.get("webdriver")
        logger.warning(
            "BLOCKED url=%s status=%d vendor=%s webdriver=%s cdc_markers=%s",
            resp.url,
            resp.status,
            vendor or "unknown",
            wd,
            cdc,
        )

    def _persist(self, t: BlockTelemetry) -> None:
        if self._log_dir is None:
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            ts = int(time.time())
            slug = t.url.split("//")[-1].split("/")[0].replace(".", "_")
            base = self._log_dir / f"{ts}_{slug}_{t.status}"

            payload = {
                "url": t.url,
                "status": t.status,
                "antibot_vendor": t.antibot_vendor,
                "response_headers": t.response_headers,
                "response_body_snippet": t.response_body_snippet,
                "console_errors": t.console_errors,
                "network_log": t.network_log,
                "timing": t.timing,
                "js_detection_signals": t.js_detection_signals,
            }
            base.with_suffix(".json").write_text(json.dumps(payload, indent=2))

            if t.screenshot_b64:
                base.with_suffix(".png").write_bytes(base64.b64decode(t.screenshot_b64))

            logger.info("Block telemetry saved → %s.json", base)
        except Exception as exc:
            logger.debug("Could not persist block telemetry: %s", exc)
