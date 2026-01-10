"""
External OSINT API integrations.

Provides integration with Shodan, URLScan.io, VirusTotal, SecurityTrails,
and other OSINT services.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ShodanResult:
    """Shodan API result."""

    ip: str
    hostnames: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)
    vulns: list[str] = field(default_factory=list)
    org: str | None = None
    isp: str | None = None
    country: str | None = None
    city: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class URLScanResult:
    """URLScan.io result."""

    url: str
    scan_id: str | None = None
    screenshot_url: str | None = None
    verdict: str | None = None
    malicious: bool = False
    technologies: list[str] = field(default_factory=list)
    ip: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class VirusTotalResult:
    """VirusTotal result."""

    target: str  # URL, domain, or IP
    malicious: int = 0
    suspicious: int = 0
    clean: int = 0
    undetected: int = 0
    reputation: int = 0
    categories: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class ShodanClient:
    """
    Shodan API client.

    Requires API key from https://account.shodan.io
    """

    BASE_URL = "https://api.shodan.io"

    def __init__(self, api_key: str | None = None):
        """
        Initialize Shodan client.

        Args:
            api_key: Shodan API key (or set SHODAN_API_KEY env var)
        """
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def host(self, ip: str) -> ShodanResult | None:
        """
        Get Shodan information for an IP address.

        Args:
            ip: IP address

        Returns:
            ShodanResult or None if API key not set
        """
        if not self.api_key:
            logger.warning("Shodan API key not configured")
            return None

        try:
            url = f"{self.BASE_URL}/shodan/host/{ip}"
            params = {"key": self.api_key}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            return ShodanResult(
                ip=ip,
                hostnames=data.get("hostnames", []),
                ports=data.get("ports", []),
                vulns=data.get("vulns", []),
                org=data.get("org"),
                isp=data.get("isp"),
                country=data.get("country_name"),
                city=data.get("city"),
                data=data,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"No Shodan data found for {ip}")
            else:
                logger.error(f"Shodan API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Shodan lookup failed for {ip}: {e}")
            return None

    async def search(self, query: str, limit: int = 100) -> list[dict]:
        """
        Search Shodan.

        Args:
            query: Shodan search query
            limit: Max results

        Returns:
            List of search results
        """
        if not self.api_key:
            logger.warning("Shodan API key not configured")
            return []

        try:
            url = f"{self.BASE_URL}/shodan/host/search"
            params = {"key": self.api_key, "query": query}

            response = await self.client.get(url, params=params)
            response.raise_for_status()

            data = response.json()
            matches = data.get("matches", [])

            return matches[:limit]

        except Exception as e:
            logger.error(f"Shodan search failed for '{query}': {e}")
            return []


class URLScanClient:
    """
    URLScan.io API client.

    Public API, no key required for basic usage.
    """

    BASE_URL = "https://urlscan.io/api/v1"

    def __init__(self, api_key: str | None = None):
        """
        Initialize URLScan client.

        Args:
            api_key: URLScan API key (optional, for higher rate limits)
        """
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def scan(self, url: str, public: bool = False) -> URLScanResult | None:
        """
        Submit URL for scanning.

        Args:
            url: URL to scan
            public: Make scan public

        Returns:
            URLScanResult with scan ID
        """
        try:
            headers = {}
            if self.api_key:
                headers["API-Key"] = self.api_key

            payload = {"url": url, "visibility": "public" if public else "private"}

            response = await self.client.post(
                f"{self.BASE_URL}/scan/",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            scan_id = data.get("uuid")

            # Wait a bit for scan to complete
            await asyncio.sleep(5)

            # Fetch results
            return await self.result(scan_id) if scan_id else None

        except Exception as e:
            logger.error(f"URLScan submission failed for {url}: {e}")
            return None

    async def result(self, scan_id: str) -> URLScanResult | None:
        """
        Get scan results.

        Args:
            scan_id: Scan UUID

        Returns:
            URLScanResult or None
        """
        try:
            response = await self.client.get(f"{self.BASE_URL}/result/{scan_id}/")
            response.raise_for_status()

            data = response.json()

            verdict = data.get("verdicts", {})
            page = data.get("page", {})

            return URLScanResult(
                url=page.get("url", ""),
                scan_id=scan_id,
                screenshot_url=data.get("task", {}).get("screenshotURL"),
                verdict=verdict.get("overall", {}).get("verdict"),
                malicious=verdict.get("overall", {}).get("malicious", False),
                technologies=data.get("meta", {}).get("processors", {}).get("wappa", {}).get("data", []),
                ip=page.get("ip"),
                data=data,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"URLScan results not ready for {scan_id}")
            return None
        except Exception as e:
            logger.error(f"URLScan result fetch failed for {scan_id}: {e}")
            return None


class VirusTotalClient:
    """
    VirusTotal API client.

    Requires API key from https://www.virustotal.com
    """

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self, api_key: str | None = None):
        """
        Initialize VirusTotal client.

        Args:
            api_key: VirusTotal API key
        """
        self.api_key = api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def url(self, url: str) -> VirusTotalResult | None:
        """
        Get VirusTotal report for URL.

        Args:
            url: URL to check

        Returns:
            VirusTotalResult or None
        """
        if not self.api_key:
            logger.warning("VirusTotal API key not configured")
            return None

        try:
            import base64

            # URL ID is base64 of URL without padding
            url_id = base64.urlsafe_b64encode(url.encode()).decode().strip("=")

            headers = {"x-apikey": self.api_key}
            response = await self.client.get(
                f"{self.BASE_URL}/urls/{url_id}",
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})

            return VirusTotalResult(
                target=url,
                malicious=stats.get("malicious", 0),
                suspicious=stats.get("suspicious", 0),
                clean=stats.get("harmless", 0),
                undetected=stats.get("undetected", 0),
                reputation=attributes.get("reputation", 0),
                categories=list(attributes.get("categories", {}).values()),
                data=data,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"No VirusTotal data for {url}")
            return None
        except Exception as e:
            logger.error(f"VirusTotal lookup failed for {url}: {e}")
            return None

    async def domain(self, domain: str) -> VirusTotalResult | None:
        """
        Get VirusTotal report for domain.

        Args:
            domain: Domain to check

        Returns:
            VirusTotalResult or None
        """
        if not self.api_key:
            logger.warning("VirusTotal API key not configured")
            return None

        try:
            headers = {"x-apikey": self.api_key}
            response = await self.client.get(
                f"{self.BASE_URL}/domains/{domain}",
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})

            return VirusTotalResult(
                target=domain,
                malicious=stats.get("malicious", 0),
                suspicious=stats.get("suspicious", 0),
                clean=stats.get("harmless", 0),
                undetected=stats.get("undetected", 0),
                reputation=attributes.get("reputation", 0),
                categories=list(attributes.get("categories", {}).values()),
                data=data,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"No VirusTotal data for {domain}")
            return None
        except Exception as e:
            logger.error(f"VirusTotal lookup failed for {domain}: {e}")
            return None


class OSINTAggregator:
    """
    Aggregate results from multiple OSINT APIs.

    Combines Shodan, URLScan, VirusTotal, and other sources.
    """

    def __init__(
        self,
        shodan_key: str | None = None,
        urlscan_key: str | None = None,
        virustotal_key: str | None = None,
    ):
        """
        Initialize OSINT aggregator.

        Args:
            shodan_key: Shodan API key
            urlscan_key: URLScan API key
            virustotal_key: VirusTotal API key
        """
        self.shodan = ShodanClient(shodan_key) if shodan_key else None
        self.urlscan = URLScanClient(urlscan_key)
        self.virustotal = VirusTotalClient(virustotal_key) if virustotal_key else None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.shodan:
            await self.shodan.__aexit__(exc_type, exc_val, exc_tb)
        if self.urlscan:
            await self.urlscan.__aexit__(exc_type, exc_val, exc_tb)
        if self.virustotal:
            await self.virustotal.__aexit__(exc_type, exc_val, exc_tb)

    async def investigate_ip(self, ip: str) -> dict[str, Any]:
        """
        Investigate IP across multiple sources.

        Args:
            ip: IP address

        Returns:
            Aggregated results
        """
        results = {"ip": ip, "sources": {}}

        # Shodan
        if self.shodan:
            shodan_result = await self.shodan.host(ip)
            if shodan_result:
                results["sources"]["shodan"] = shodan_result

        return results

    async def investigate_domain(self, domain: str) -> dict[str, Any]:
        """
        Investigate domain across multiple sources.

        Args:
            domain: Domain name

        Returns:
            Aggregated results
        """
        results = {"domain": domain, "sources": {}}

        # VirusTotal
        if self.virustotal:
            vt_result = await self.virustotal.domain(domain)
            if vt_result:
                results["sources"]["virustotal"] = vt_result

        return results

    async def investigate_url(self, url: str) -> dict[str, Any]:
        """
        Investigate URL across multiple sources.

        Args:
            url: URL to investigate

        Returns:
            Aggregated results
        """
        results = {"url": url, "sources": {}}

        # URLScan
        urlscan_result = await self.urlscan.scan(url)
        if urlscan_result:
            results["sources"]["urlscan"] = urlscan_result

        # VirusTotal
        if self.virustotal:
            vt_result = await self.virustotal.url(url)
            if vt_result:
                results["sources"]["virustotal"] = vt_result

        return results
