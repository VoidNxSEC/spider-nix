"""
Web intelligence extraction tools.

Provides structured data extraction, sitemap parsing, robots.txt analysis,
and web archive integration for comprehensive competitive intelligence.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class StructuredData:
    """Extracted structured data from web page."""

    url: str
    schema_type: str  # Organization, Product, Article, etc.
    format: Literal["json-ld", "microdata", "opengraph", "twitter"]
    data: dict
    properties: dict = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class SitemapURL:
    """URL entry from sitemap."""

    loc: str
    lastmod: datetime | None = None
    changefreq: str | None = None
    priority: float | None = None
    source_sitemap: str = ""


@dataclass
class SitemapAnalysis:
    """Parsed sitemap data with analytics."""

    sitemap_url: str
    url_count: int
    urls: list[SitemapURL]
    nested_sitemaps: list[str] = field(default_factory=list)
    url_patterns: dict[str, int] = field(default_factory=dict)


@dataclass
class RobotsRule:
    """Robots.txt rule for user agent."""

    user_agent: str
    disallowed_paths: list[str] = field(default_factory=list)
    allowed_paths: list[str] = field(default_factory=list)


@dataclass
class RobotsAnalysis:
    """Parsed robots.txt data."""

    url: str
    rules: list[RobotsRule]
    sitemaps: list[str] = field(default_factory=list)
    crawl_delay: int | None = None
    interesting_paths: list[str] = field(default_factory=list)


@dataclass
class ArchiveSnapshot:
    """Web archive snapshot information."""

    url: str
    timestamp: datetime
    archive_url: str
    status_code: int
    digest: str | None = None


@dataclass
class ArchiveTimeline:
    """Timeline of web archive snapshots."""

    url: str
    snapshot_count: int
    snapshots: list[ArchiveSnapshot]
    first_seen: datetime | None = None
    last_seen: datetime | None = None


# ============================================================================
# Structured Data Extractor
# ============================================================================


class StructuredDataExtractor:
    """
    Extract structured data from web pages.

    Supports multiple formats:
    - JSON-LD (schema.org)
    - Open Graph Protocol
    - Twitter Cards
    - HTML5 Microdata
    """

    async def extract(self, url: str, html: str) -> list[StructuredData]:
        """
        Extract all structured data formats from HTML.

        Args:
            url: Page URL
            html: HTML content

        Returns:
            List of extracted structured data
        """
        results = []

        results.extend(self._extract_json_ld(url, html))
        results.extend(self._extract_opengraph(url, html))
        results.extend(self._extract_twitter_cards(url, html))
        results.extend(self._extract_microdata(url, html))

        return results

    def _extract_json_ld(self, url: str, html: str) -> list[StructuredData]:
        """Extract JSON-LD structured data."""
        results = []

        # Find all JSON-LD script tags
        pattern = r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        matches = re.finditer(pattern, html, re.IGNORECASE | re.DOTALL)

        for match in matches:
            try:
                json_content = match.group(1).strip()
                data = json.loads(json_content)

                # Handle array of items
                items = data if isinstance(data, list) else [data]

                for item in items:
                    schema_type = item.get("@type", "Unknown")

                    # Extract key properties
                    properties = {}
                    if "@context" in item:
                        del item["@context"]  # Remove context for cleaner properties

                    for key, value in item.items():
                        if not key.startswith("@"):
                            properties[key] = value

                    results.append(
                        StructuredData(
                            url=url,
                            schema_type=schema_type,
                            format="json-ld",
                            data=item,
                            properties=properties,
                            confidence=1.0,
                        )
                    )

            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse JSON-LD: {e}")

        return results

    def _extract_opengraph(self, url: str, html: str) -> list[StructuredData]:
        """Extract Open Graph metadata."""
        og_data = {}

        # Find all og: meta tags
        pattern = r'<meta\s+property\s*=\s*["\']og:([^"\']+)["\']\s+content\s*=\s*["\']([^"\']*)["\']'
        matches = re.finditer(pattern, html, re.IGNORECASE)

        for match in matches:
            property_name = match.group(1)
            content = match.group(2)
            og_data[property_name] = content

        if og_data:
            schema_type = og_data.get("type", "WebPage")

            return [
                StructuredData(
                    url=url,
                    schema_type=schema_type,
                    format="opengraph",
                    data=og_data,
                    properties=og_data,
                    confidence=0.9,
                )
            ]

        return []

    def _extract_twitter_cards(self, url: str, html: str) -> list[StructuredData]:
        """Extract Twitter Card metadata."""
        twitter_data = {}

        # Find all twitter: meta tags
        pattern = r'<meta\s+(?:name|property)\s*=\s*["\']twitter:([^"\']+)["\']\s+content\s*=\s*["\']([^"\']*)["\']'
        matches = re.finditer(pattern, html, re.IGNORECASE)

        for match in matches:
            property_name = match.group(1)
            content = match.group(2)
            twitter_data[property_name] = content

        if twitter_data:
            card_type = twitter_data.get("card", "summary")

            return [
                StructuredData(
                    url=url,
                    schema_type=f"TwitterCard:{card_type}",
                    format="twitter",
                    data=twitter_data,
                    properties=twitter_data,
                    confidence=0.9,
                )
            ]

        return []

    def _extract_microdata(self, url: str, html: str) -> list[StructuredData]:
        """Extract HTML5 microdata."""
        results = []

        # Find elements with itemscope
        itemscope_pattern = r'<[^>]+itemscope[^>]+itemtype\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</[^>]+>'
        matches = re.finditer(itemscope_pattern, html, re.IGNORECASE | re.DOTALL)

        for match in matches:
            item_type = match.group(1)
            item_html = match.group(2)

            # Extract schema type from URL
            schema_type = item_type.split("/")[-1] if "/" in item_type else item_type

            # Extract itemprop values
            properties = {}
            prop_pattern = r'itemprop\s*=\s*["\']([^"\']+)["\']\s+content\s*=\s*["\']([^"\']*)["\']'
            prop_matches = re.finditer(prop_pattern, item_html, re.IGNORECASE)

            for prop_match in prop_matches:
                prop_name = prop_match.group(1)
                prop_value = prop_match.group(2)
                properties[prop_name] = prop_value

            if properties:
                results.append(
                    StructuredData(
                        url=url,
                        schema_type=schema_type,
                        format="microdata",
                        data={"itemtype": item_type, "properties": properties},
                        properties=properties,
                        confidence=0.8,
                    )
                )

        return results


# ============================================================================
# Sitemap Parser
# ============================================================================


class SitemapParser:
    """
    Parse XML sitemaps and extract URLs.

    Supports both regular sitemaps and sitemap indexes with
    recursive parsing capability.
    """

    async def parse(
        self,
        sitemap_url: str,
        recursive: bool = True,
    ) -> SitemapAnalysis:
        """
        Parse sitemap and extract all URLs.

        Args:
            sitemap_url: Sitemap URL (usually /sitemap.xml)
            recursive: Follow nested sitemaps if True

        Returns:
            Sitemap analysis with all URLs
        """
        all_urls = []
        nested_sitemaps = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            urls, nested = await self._parse_sitemap(client, sitemap_url, recursive)
            all_urls.extend(urls)
            nested_sitemaps.extend(nested)

        # Analyze URL patterns
        url_patterns = self._analyze_patterns([u.loc for u in all_urls])

        return SitemapAnalysis(
            sitemap_url=sitemap_url,
            url_count=len(all_urls),
            urls=all_urls,
            nested_sitemaps=nested_sitemaps,
            url_patterns=url_patterns,
        )

    async def _parse_sitemap(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        recursive: bool,
    ) -> tuple[list[SitemapURL], list[str]]:
        """Parse a single sitemap file."""
        try:
            response = await client.get(sitemap_url)
            if response.status_code != 200:
                logger.warning(f"Sitemap {sitemap_url} returned {response.status_code}")
                return [], []

            return self._parse_xml(sitemap_url, response.text, client, recursive)

        except httpx.RequestError as e:
            logger.error(f"Error fetching sitemap {sitemap_url}: {e}")
            return [], []

    def _parse_xml(
        self,
        source_url: str,
        xml_content: str,
        client: httpx.AsyncClient | None,
        recursive: bool,
    ) -> tuple[list[SitemapURL], list[str]]:
        """Parse sitemap XML content."""
        urls = []
        nested_sitemaps = []

        try:
            root = ET.fromstring(xml_content)

            # Remove namespace from tags for easier parsing
            for elem in root.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]

            # Check if it's a sitemap index
            if root.tag == "sitemapindex":
                for sitemap in root.findall("sitemap"):
                    loc = sitemap.find("loc")
                    if loc is not None:
                        nested_sitemaps.append(loc.text)

                # Recursively parse nested sitemaps
                if recursive and client:
                    import asyncio

                    for nested_url in nested_sitemaps:
                        loop = asyncio.get_event_loop()
                        nested_urls, more_nested = loop.run_until_complete(
                            self._parse_sitemap(client, nested_url, recursive)
                        )
                        urls.extend(nested_urls)
                        nested_sitemaps.extend(more_nested)

            # Parse regular sitemap
            elif root.tag == "urlset":
                for url_elem in root.findall("url"):
                    loc = url_elem.find("loc")
                    if loc is None:
                        continue

                    lastmod_elem = url_elem.find("lastmod")
                    changefreq_elem = url_elem.find("changefreq")
                    priority_elem = url_elem.find("priority")

                    # Parse lastmod
                    lastmod = None
                    if lastmod_elem is not None:
                        try:
                            lastmod = datetime.fromisoformat(lastmod_elem.text.replace("Z", "+00:00"))
                        except ValueError:
                            pass

                    # Parse priority
                    priority = None
                    if priority_elem is not None:
                        try:
                            priority = float(priority_elem.text)
                        except ValueError:
                            pass

                    urls.append(
                        SitemapURL(
                            loc=loc.text,
                            lastmod=lastmod,
                            changefreq=changefreq_elem.text if changefreq_elem is not None else None,
                            priority=priority,
                            source_sitemap=source_url,
                        )
                    )

        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")

        return urls, nested_sitemaps

    def _analyze_patterns(self, urls: list[str]) -> dict[str, int]:
        """Analyze URL patterns to identify site structure."""
        patterns = {}

        for url in urls:
            parsed = urlparse(url)
            path = parsed.path

            # Extract pattern (e.g., /blog/* or /products/*)
            parts = [p for p in path.split("/") if p]
            if parts:
                pattern = f"/{parts[0]}/*"
                patterns[pattern] = patterns.get(pattern, 0) + 1

        return patterns


# ============================================================================
# Robots.txt Analyzer
# ============================================================================


class RobotsTxtAnalyzer:
    """
    Parse and analyze robots.txt files.

    Extracts crawl rules, sitemaps, delays, and identifies
    potentially interesting disallowed paths.
    """

    INTERESTING_KEYWORDS = [
        "admin", "api", "private", "internal", "v1", "v2",
        "graphql", "backup", "config", "dashboard", "portal",
        "staging", "dev", "test",
    ]

    async def analyze(self, domain: str) -> RobotsAnalysis:
        """
        Fetch and analyze robots.txt.

        Args:
            domain: Domain URL (e.g., https://example.com)

        Returns:
            Parsed robots.txt analysis
        """
        # Ensure domain has protocol
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"

        url = urljoin(domain, "/robots.txt")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning(f"robots.txt returned {response.status_code}")
                    return RobotsAnalysis(url=url, rules=[])

                return self._parse_robots(url, response.text)

        except httpx.RequestError as e:
            logger.error(f"Error fetching robots.txt: {e}")
            return RobotsAnalysis(url=url, rules=[])

    def _parse_robots(self, url: str, content: str) -> RobotsAnalysis:
        """Parse robots.txt content."""
        rules = []
        sitemaps = []
        crawl_delay = None
        current_agent = None
        current_disallowed = []
        current_allowed = []

        for line in content.splitlines():
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse directives
            if ":" in line:
                directive, value = line.split(":", 1)
                directive = directive.strip().lower()
                value = value.strip()

                if directive == "user-agent":
                    # Save previous agent's rules
                    if current_agent:
                        rules.append(
                            RobotsRule(
                                user_agent=current_agent,
                                disallowed_paths=current_disallowed.copy(),
                                allowed_paths=current_allowed.copy(),
                            )
                        )

                    current_agent = value
                    current_disallowed = []
                    current_allowed = []

                elif directive == "disallow":
                    if current_agent and value:
                        current_disallowed.append(value)

                elif directive == "allow":
                    if current_agent and value:
                        current_allowed.append(value)

                elif directive == "sitemap":
                    sitemaps.append(value)

                elif directive == "crawl-delay":
                    try:
                        crawl_delay = int(value)
                    except ValueError:
                        pass

        # Save last agent's rules
        if current_agent:
            rules.append(
                RobotsRule(
                    user_agent=current_agent,
                    disallowed_paths=current_disallowed.copy(),
                    allowed_paths=current_allowed.copy(),
                )
            )

        # Find interesting paths
        interesting_paths = self._extract_interesting_paths(rules)

        return RobotsAnalysis(
            url=url,
            rules=rules,
            sitemaps=sitemaps,
            crawl_delay=crawl_delay,
            interesting_paths=interesting_paths,
        )

    def _extract_interesting_paths(self, rules: list[RobotsRule]) -> list[str]:
        """Extract potentially interesting disallowed paths."""
        interesting = set()

        for rule in rules:
            for path in rule.disallowed_paths:
                # Check if path contains interesting keywords
                path_lower = path.lower()
                if any(keyword in path_lower for keyword in self.INTERESTING_KEYWORDS):
                    interesting.add(path)

        return sorted(interesting)


# ============================================================================
# Web Archive Client
# ============================================================================


class WebArchiveClient:
    """
    Integrate with Wayback Machine API.

    Retrieves historical snapshots and timeline data for
    competitive intelligence and change tracking.
    """

    WAYBACK_API = "https://web.archive.org/cdx/search/cdx"
    WAYBACK_SNAPSHOT = "https://web.archive.org/web/{timestamp}/{url}"

    async def get_timeline(
        self,
        url: str,
        limit: int = 100,
        from_date: datetime | None = None,
    ) -> ArchiveTimeline:
        """
        Get archive timeline for URL.

        Args:
            url: URL to query
            limit: Maximum snapshots to retrieve
            from_date: Start date for snapshots

        Returns:
            Timeline with snapshot information
        """
        params = {
            "url": url,
            "output": "json",
            "limit": str(limit),
        }

        if from_date:
            params["from"] = from_date.strftime("%Y%m%d")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.WAYBACK_API, params=params)

                if response.status_code != 200:
                    logger.warning(f"Wayback API returned {response.status_code}")
                    return ArchiveTimeline(url=url, snapshot_count=0, snapshots=[])

                return self._parse_cdx_response(url, response.text)

        except httpx.RequestError as e:
            logger.error(f"Error querying Wayback API: {e}")
            return ArchiveTimeline(url=url, snapshot_count=0, snapshots=[])

    def _parse_cdx_response(self, url: str, response_text: str) -> ArchiveTimeline:
        """Parse CDX API JSON response."""
        try:
            data = json.loads(response_text)

            if not data or len(data) < 2:
                return ArchiveTimeline(url=url, snapshot_count=0, snapshots=[])

            # First row is headers
            headers = data[0]
            rows = data[1:]

            snapshots = []

            for row in rows:
                try:
                    # CDX format: timestamp, original, mimetype, statuscode, digest, length
                    timestamp_str = row[headers.index("timestamp")]
                    status_code = int(row[headers.index("statuscode")])
                    digest = row[headers.index("digest")] if "digest" in headers else None

                    # Parse timestamp (format: YYYYMMDDHHmmss)
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")

                    archive_url = self.WAYBACK_SNAPSHOT.format(
                        timestamp=timestamp_str,
                        url=url,
                    )

                    snapshots.append(
                        ArchiveSnapshot(
                            url=url,
                            timestamp=timestamp,
                            archive_url=archive_url,
                            status_code=status_code,
                            digest=digest,
                        )
                    )

                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing CDX row: {e}")
                    continue

            # Determine first and last seen
            first_seen = min((s.timestamp for s in snapshots), default=None)
            last_seen = max((s.timestamp for s in snapshots), default=None)

            return ArchiveTimeline(
                url=url,
                first_seen=first_seen,
                last_seen=last_seen,
                snapshot_count=len(snapshots),
                snapshots=snapshots,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CDX JSON: {e}")
            return ArchiveTimeline(url=url, snapshot_count=0, snapshots=[])

    async def get_snapshot(self, url: str, timestamp: datetime) -> str | None:
        """
        Fetch archived snapshot content.

        Args:
            url: Original URL
            timestamp: Snapshot timestamp

        Returns:
            Archived page content or None
        """
        timestamp_str = timestamp.strftime("%Y%m%d%H%M%S")
        archive_url = self.WAYBACK_SNAPSHOT.format(timestamp=timestamp_str, url=url)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(archive_url)

                if response.status_code == 200:
                    return response.text

        except httpx.RequestError as e:
            logger.error(f"Error fetching snapshot: {e}")

        return None
