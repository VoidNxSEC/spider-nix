"""Core crawler implementation using httpx with stealth."""

import asyncio
import time
from typing import AsyncGenerator, Callable
from urllib.parse import urljoin, urlparse

import httpx
from rich.console import Console

from .config import CrawlerConfig
from .proxy import ProxyRotator
from .rate_limiter import (
    AdaptiveRateLimiter,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    RequestDeduplicator,
)
from .stealth import StealthEngine
from .storage import CrawlResult, StorageBackend, get_storage

console = Console()


class SpiderNix:
    """Enterprise web crawler with anti-detection and proxy rotation."""

    def __init__(
        self,
        config: CrawlerConfig | None = None,
        proxy_rotator: ProxyRotator | None = None,
        enable_adaptive_rate_limiting: bool = True,
        enable_circuit_breaker: bool = True,
        enable_deduplication: bool = True,
    ):
        self.config = config or CrawlerConfig()
        self.proxy = proxy_rotator or ProxyRotator(
            proxies=self.config.proxy.urls,
            strategy=self.config.proxy.rotation_strategy,
        )
        self.stealth = StealthEngine()

        # Advanced features
        self.rate_limiter = AdaptiveRateLimiter(
            initial_delay_ms=self.config.stealth.min_delay_ms,
            min_delay_ms=self.config.stealth.min_delay_ms,
            max_delay_ms=self.config.stealth.max_delay_ms,
        ) if enable_adaptive_rate_limiting else None

        self.circuit_breaker = CircuitBreaker() if enable_circuit_breaker else None
        self.deduplicator = RequestDeduplicator() if enable_deduplication else None

        self._visited: set[str] = set()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._results: list[CrawlResult] = []
        self._running = False
    
    async def crawl(
        self,
        start_url: str,
        max_pages: int | None = None,
        follow_links: bool = False,
        link_filter: Callable[[str], bool] | None = None,
        storage: StorageBackend | None = None,
    ) -> list[CrawlResult]:
        """
        Crawl starting from a URL.
        
        Args:
            start_url: Starting URL
            max_pages: Max pages to crawl (overrides config)
            follow_links: Whether to follow links on pages
            link_filter: Function to filter which links to follow
            storage: Optional storage backend for results
        """
        max_pages = max_pages or self.config.max_requests_per_crawl
        self._running = True
        self._visited.clear()
        self._results.clear()
        
        await self._queue.put(start_url)
        
        tasks = []
        for _ in range(self.config.max_concurrent_requests):
            task = asyncio.create_task(
                self._worker(max_pages, follow_links, link_filter, storage)
            )
            tasks.append(task)
        
        # Wait for queue to empty
        await self._queue.join()
        self._running = False
        
        # Cancel workers
        for task in tasks:
            task.cancel()
        
        if storage:
            await storage.close()
        
        return self._results
    
    async def _worker(
        self,
        max_pages: int,
        follow_links: bool,
        link_filter: Callable[[str], bool] | None,
        storage: StorageBackend | None,
    ):
        """Worker coroutine that processes URLs from queue."""
        async with httpx.AsyncClient(
            timeout=self.config.request_timeout_ms / 1000,
            follow_redirects=True,
        ) as client:
            while self._running:
                try:
                    url = await asyncio.wait_for(self._queue.get(), timeout=2)
                except asyncio.TimeoutError:
                    continue
                
                try:
                    if url in self._visited or len(self._visited) >= max_pages:
                        continue
                    
                    self._visited.add(url)
                    result = await self._fetch_with_retry(client, url)
                    
                    if result:
                        self._results.append(result)
                        
                        if storage:
                            await storage.save(result)
                        
                        console.print(f"[green]✓[/] {url} ({result.status_code})")
                        
                        # Follow links
                        if follow_links and result.status_code == 200:
                            links = self._extract_links(result.content, url)
                            for link in links:
                                if link not in self._visited:
                                    if link_filter is None or link_filter(link):
                                        await self._queue.put(link)
                    
                finally:
                    self._queue.task_done()
    
    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> CrawlResult | None:
        """Fetch URL with retry logic and proxy rotation."""
        # Check for duplicate URL
        if self.deduplicator and await self.deduplicator.is_duplicate_url(url):
            console.print(f"[dim]⊗[/] {url} (duplicate URL, skipped)")
            return None

        # Apply rate limiting
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        last_error = None

        for attempt in range(self.config.max_retries):
            proxy_url = self.proxy.get_next()
            headers = self.stealth.get_headers()

            try:
                # Circuit breaker protection
                if self.circuit_breaker:
                    try:
                        result = await self.circuit_breaker.call(
                            self._do_request,
                            client,
                            url,
                            headers,
                            proxy_url,
                            attempt,
                        )
                        return result
                    except CircuitBreakerError as e:
                        console.print(f"[red]⚠[/] {url} circuit breaker open, skipping")
                        return None
                else:
                    result = await self._do_request(
                        client,
                        url,
                        headers,
                        proxy_url,
                        attempt,
                    )
                    return result

            except httpx.RequestError as e:
                last_error = e
                if proxy_url:
                    self.proxy.report_failure(proxy_url)

                # Report to rate limiter
                if self.rate_limiter:
                    await self.rate_limiter.report_request(
                        status_code=0,
                        response_time_ms=0,
                        error=True,
                    )

                console.print(f"[red]✗[/] {url} error: {e}, retrying...")
                await asyncio.sleep(1)

        console.print(f"[red]✗[/] {url} failed after {self.config.max_retries} attempts")
        return None

    async def _do_request(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        proxy_url: str | None,
        attempt: int,
    ) -> CrawlResult | None:
        """Execute single HTTP request."""
        start = time.monotonic()

        # Configure proxy if available
        if proxy_url:
            client._mounts = {
                "http://": httpx.HTTPTransport(proxy=proxy_url),
                "https://": httpx.HTTPTransport(proxy=proxy_url),
            }

        response = await client.get(url, headers=headers)
        elapsed_ms = (time.monotonic() - start) * 1000

        # Report to rate limiter
        if self.rate_limiter:
            await self.rate_limiter.report_request(
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                error=False,
            )

        # Report proxy stats
        if proxy_url:
            if response.status_code in self.config.retry_on_status_codes:
                self.proxy.report_blocked(proxy_url)
            else:
                self.proxy.report_success(proxy_url, elapsed_ms)

        # Check if blocked
        if response.status_code in self.config.retry_on_status_codes:
            console.print(f"[yellow]⚠[/] {url} blocked ({response.status_code}), retrying...")

            # Human-like delay before retry
            if self.config.stealth.human_like_delays:
                delay = self.stealth.get_random_delay_ms(
                    self.config.stealth.min_delay_ms,
                    self.config.stealth.max_delay_ms,
                ) / 1000
                await asyncio.sleep(delay)

            raise httpx.RequestError(f"Blocked with status {response.status_code}")

        # Check for duplicate content
        if self.deduplicator and await self.deduplicator.is_duplicate_content(response.text):
            console.print(f"[dim]⊗[/] {url} (duplicate content, skipped)")
            return None

        return CrawlResult(
            url=url,
            status_code=response.status_code,
            content=response.text,
            headers=dict(response.headers),
            metadata={
                "elapsed_ms": elapsed_ms,
                "proxy": proxy_url,
                "attempt": attempt + 1,
                "rate_limit_delay_ms": self.rate_limiter.current_delay_ms if self.rate_limiter else 0,
                "circuit_state": self.circuit_breaker.get_state().value if self.circuit_breaker else "none",
            }
        )
    
    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract links from HTML."""
        import re
        
        links = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', html):
            href = match.group(1)
            # Convert relative to absolute
            full_url = urljoin(base_url, href)
            # Only same domain
            if urlparse(full_url).netloc == urlparse(base_url).netloc:
                links.append(full_url)
        
        return list(set(links))


async def quick_crawl(url: str, pages: int = 10) -> list[CrawlResult]:
    """Quick crawl helper function."""
    spider = SpiderNix()
    return await spider.crawl(url, max_pages=pages)
