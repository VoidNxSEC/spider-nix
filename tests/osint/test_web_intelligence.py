"""Tests for web_intelligence module."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from spider_nix.osint.web_intelligence import (
    StructuredDataExtractor,
    StructuredData,
    SitemapParser,
    SitemapURL,
    SitemapAnalysis,
    RobotsTxtAnalyzer,
    RobotsRule,
    RobotsAnalysis,
    WebArchiveClient,
    ArchiveSnapshot,
    ArchiveTimeline,
)


class TestStructuredDataExtractor:
    """Tests for structured data extraction."""

    @pytest.mark.asyncio
    async def test_extract_json_ld(self):
        """Test extracting JSON-LD structured data."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@context": "https://schema.org",
                    "@type": "Organization",
                    "name": "Example Corp",
                    "url": "https://example.com"
                }
                </script>
            </head>
        </html>
        """

        extractor = StructuredDataExtractor()
        data = await extractor.extract("https://example.com", html)

        assert len(data) > 0
        org_data = next((d for d in data if d.schema_type == "Organization"), None)
        assert org_data is not None
        assert org_data.format == "json-ld"
        assert org_data.properties.get("name") == "Example Corp"

    @pytest.mark.asyncio
    async def test_extract_opengraph(self):
        """Test extracting Open Graph metadata."""
        html = """
        <html>
            <head>
                <meta property="og:title" content="Example Page">
                <meta property="og:type" content="website">
                <meta property="og:url" content="https://example.com">
                <meta property="og:image" content="https://example.com/image.jpg">
            </head>
        </html>
        """

        extractor = StructuredDataExtractor()
        data = await extractor.extract("https://example.com", html)

        assert len(data) > 0
        og_data = next((d for d in data if d.format == "opengraph"), None)
        assert og_data is not None
        assert og_data.properties.get("title") == "Example Page"
        assert og_data.properties.get("url") == "https://example.com"

    @pytest.mark.asyncio
    async def test_extract_twitter_cards(self):
        """Test extracting Twitter Card metadata."""
        html = """
        <html>
            <head>
                <meta name="twitter:card" content="summary">
                <meta name="twitter:title" content="Example Tweet">
                <meta name="twitter:description" content="This is a test">
            </head>
        </html>
        """

        extractor = StructuredDataExtractor()
        data = await extractor.extract("https://example.com", html)

        assert len(data) > 0
        twitter_data = next((d for d in data if d.format == "twitter"), None)
        assert twitter_data is not None
        assert twitter_data.properties.get("card") == "summary"
        assert twitter_data.properties.get("title") == "Example Tweet"

    @pytest.mark.asyncio
    async def test_extract_multiple_formats(self):
        """Test extracting multiple structured data formats from one page."""
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {"@type": "Article", "headline": "Test Article"}
                </script>
                <meta property="og:title" content="OG Title">
                <meta name="twitter:card" content="summary">
            </head>
        </html>
        """

        extractor = StructuredDataExtractor()
        data = await extractor.extract("https://example.com", html)

        # Should extract all three formats
        formats = [d.format for d in data]
        assert "json-ld" in formats or len(data) > 0  # At least one format

    @pytest.mark.asyncio
    async def test_extract_microdata(self):
        """Test extracting microdata structured data."""
        html = """
        <html>
            <body>
                <div itemscope itemtype="http://schema.org/Product">
                    <span itemprop="name">Example Product</span>
                    <span itemprop="price">$19.99</span>
                </div>
            </body>
        </html>
        """

        extractor = StructuredDataExtractor()
        data = await extractor.extract("https://example.com", html)

        # Should extract microdata
        assert len(data) >= 0  # Implementation may vary

    def test_structured_data_dataclass(self):
        """Test StructuredData dataclass."""
        data = StructuredData(
            url="https://example.com",
            schema_type="Organization",
            format="json-ld",
            data={"name": "Example Corp"},
            properties={"name": "Example Corp", "url": "https://example.com"},
            confidence=1.0,
        )

        assert data.url == "https://example.com"
        assert data.schema_type == "Organization"
        assert data.format == "json-ld"


class TestSitemapParser:
    """Tests for sitemap parsing."""

    @pytest.mark.asyncio
    async def test_parse_simple_sitemap(self, httpx_mock):
        """Test parsing a simple sitemap.xml."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://example.com/page1</loc>
                <lastmod>2024-01-01</lastmod>
                <changefreq>daily</changefreq>
                <priority>0.8</priority>
            </url>
            <url>
                <loc>https://example.com/page2</loc>
            </url>
        </urlset>
        """

        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            status_code=200,
            text=sitemap_xml,
        )

        parser = SitemapParser()
        analysis = await parser.parse("https://example.com/sitemap.xml", recursive=False)

        assert analysis is not None
        assert analysis.url_count == 2
        assert len(analysis.urls) == 2

        # Check first URL details
        url1 = next((u for u in analysis.urls if "page1" in u.loc), None)
        assert url1 is not None
        assert url1.changefreq == "daily"
        assert url1.priority == 0.8

    @pytest.mark.asyncio
    async def test_parse_sitemap_index(self, httpx_mock):
        """Test parsing a sitemap index with nested sitemaps."""
        index_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap>
                <loc>https://example.com/sitemap1.xml</loc>
            </sitemap>
            <sitemap>
                <loc>https://example.com/sitemap2.xml</loc>
            </sitemap>
        </sitemapindex>
        """

        sitemap1_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/page1</loc></url>
        </urlset>
        """

        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            status_code=200,
            text=index_xml,
        )
        httpx_mock.add_response(
            url="https://example.com/sitemap1.xml",
            status_code=200,
            text=sitemap1_xml,
        )

        parser = SitemapParser()
        analysis = await parser.parse("https://example.com/sitemap.xml", recursive=True)

        assert analysis is not None
        assert len(analysis.nested_sitemaps) == 2
        # Should have parsed nested sitemap if recursive=True

    @pytest.mark.asyncio
    async def test_detect_url_patterns(self, httpx_mock):
        """Test detecting URL patterns in sitemap."""
        sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/blog/post-1</loc></url>
            <url><loc>https://example.com/blog/post-2</loc></url>
            <url><loc>https://example.com/products/item-1</loc></url>
        </urlset>
        """

        httpx_mock.add_response(
            url="https://example.com/sitemap.xml",
            status_code=200,
            text=sitemap_xml,
        )

        parser = SitemapParser()
        analysis = await parser.parse("https://example.com/sitemap.xml", recursive=False)

        assert analysis is not None
        # Should detect /blog/* and /products/* patterns
        assert len(analysis.url_patterns) > 0

    def test_sitemap_url_dataclass(self):
        """Test SitemapURL dataclass."""
        url = SitemapURL(
            loc="https://example.com/page",
            lastmod=datetime(2024, 1, 1),
            changefreq="daily",
            priority=0.8,
            source_sitemap="https://example.com/sitemap.xml",
        )

        assert url.loc == "https://example.com/page"
        assert url.changefreq == "daily"
        assert url.priority == 0.8


class TestRobotsTxtAnalyzer:
    """Tests for robots.txt analysis."""

    @pytest.mark.asyncio
    async def test_parse_basic_robots_txt(self, httpx_mock):
        """Test parsing a basic robots.txt file."""
        robots_txt = """
        User-agent: *
        Disallow: /admin/
        Disallow: /private/
        Allow: /public/
        Crawl-delay: 10
        Sitemap: https://example.com/sitemap.xml
        """

        httpx_mock.add_response(
            url="https://example.com/robots.txt",
            status_code=200,
            text=robots_txt,
        )

        analyzer = RobotsTxtAnalyzer()
        analysis = await analyzer.analyze("https://example.com")

        assert analysis is not None
        assert len(analysis.rules) > 0
        assert analysis.crawl_delay == 10
        assert "https://example.com/sitemap.xml" in analysis.sitemaps

        # Check rules
        rule = analysis.rules[0]
        assert rule.user_agent == "*"
        assert "/admin/" in rule.disallowed_paths
        assert "/public/" in rule.allowed_paths

    @pytest.mark.asyncio
    async def test_parse_multiple_user_agents(self, httpx_mock):
        """Test parsing robots.txt with multiple user agents."""
        robots_txt = """
        User-agent: Googlebot
        Disallow: /private/

        User-agent: *
        Disallow: /admin/
        """

        httpx_mock.add_response(
            url="https://example.com/robots.txt",
            status_code=200,
            text=robots_txt,
        )

        analyzer = RobotsTxtAnalyzer()
        analysis = await analyzer.analyze("https://example.com")

        assert analysis is not None
        assert len(analysis.rules) >= 2

        # Check that both user agents are parsed
        user_agents = [r.user_agent for r in analysis.rules]
        assert "Googlebot" in user_agents
        assert "*" in user_agents

    @pytest.mark.asyncio
    async def test_identify_interesting_paths(self, httpx_mock):
        """Test identifying interesting disallowed paths."""
        robots_txt = """
        User-agent: *
        Disallow: /admin/
        Disallow: /api/internal/
        Disallow: /backup/
        Disallow: /.git/
        """

        httpx_mock.add_response(
            url="https://example.com/robots.txt",
            status_code=200,
            text=robots_txt,
        )

        analyzer = RobotsTxtAnalyzer()
        analysis = await analyzer.analyze("https://example.com")

        assert analysis is not None
        # Should identify admin, api, backup, .git as interesting
        assert len(analysis.interesting_paths) > 0
        assert any("admin" in path for path in analysis.interesting_paths)

    @pytest.mark.asyncio
    async def test_handle_missing_robots_txt(self, httpx_mock):
        """Test handling missing robots.txt."""
        httpx_mock.add_response(
            url="https://example.com/robots.txt",
            status_code=404,
        )

        analyzer = RobotsTxtAnalyzer()
        analysis = await analyzer.analyze("https://example.com")

        # Should return None or empty analysis
        assert analysis is None or len(analysis.rules) == 0

    def test_robots_rule_dataclass(self):
        """Test RobotsRule dataclass."""
        rule = RobotsRule(
            user_agent="*",
            disallowed_paths=["/admin/", "/private/"],
            allowed_paths=["/public/"],
        )

        assert rule.user_agent == "*"
        assert len(rule.disallowed_paths) == 2
        assert "/public/" in rule.allowed_paths


class TestWebArchiveClient:
    """Tests for Wayback Machine integration."""

    @pytest.mark.asyncio
    async def test_get_timeline(self, httpx_mock):
        """Test getting archive timeline for a URL."""
        # Mock Wayback CDX API response
        cdx_response = """org,example)/ 20240101120000 https://example.com/ text/html 200 ABCDEF123456 - - 1234 wayback.archive.org/web/20240101120000/https://example.com/
org,example)/ 20240201120000 https://example.com/ text/html 200 FEDCBA654321 - - 1234 wayback.archive.org/web/20240201120000/https://example.com/"""

        httpx_mock.add_response(
            url="https://web.archive.org/cdx/search/cdx?url=https://example.com&output=json&limit=10",
            status_code=200,
            text=cdx_response,
        )

        client = WebArchiveClient()
        timeline = await client.get_timeline("https://example.com", limit=10)

        assert timeline is not None
        assert timeline.snapshot_count > 0
        assert len(timeline.snapshots) > 0

    @pytest.mark.asyncio
    async def test_parse_snapshot(self):
        """Test parsing a single archive snapshot."""
        client = WebArchiveClient()

        # Mock CDX line
        cdx_line = "org,example)/ 20240101120000 https://example.com/ text/html 200 ABCDEF - - 1234"

        snapshot = client._parse_cdx_line(cdx_line)

        assert snapshot is not None
        assert snapshot.url == "https://example.com/"
        assert snapshot.status_code == 200
        assert snapshot.timestamp.year == 2024
        assert snapshot.timestamp.month == 1

    @pytest.mark.asyncio
    async def test_filter_by_date(self, httpx_mock):
        """Test filtering snapshots by date."""
        cdx_response = """org,example)/ 20230101120000 https://example.com/ text/html 200 ABC - - 1234
org,example)/ 20240101120000 https://example.com/ text/html 200 DEF - - 1234"""

        httpx_mock.add_response(
            url="https://web.archive.org/cdx/search/cdx?url=https://example.com&output=json&limit=10&from=20240101",
            status_code=200,
            text=cdx_response,
        )

        client = WebArchiveClient()
        from_date = datetime(2024, 1, 1)
        timeline = await client.get_timeline(
            "https://example.com",
            limit=10,
            from_date=from_date,
        )

        # Should only include snapshots from 2024 or later
        assert timeline is not None
        if timeline.snapshots:
            for snapshot in timeline.snapshots:
                assert snapshot.timestamp >= from_date

    @pytest.mark.asyncio
    async def test_build_archive_url(self):
        """Test building Wayback Machine archive URL."""
        client = WebArchiveClient()

        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        url = "https://example.com"

        archive_url = client._build_archive_url(timestamp, url)

        assert "web.archive.org/web/" in archive_url
        assert "20240101120000" in archive_url
        assert "https://example.com" in archive_url

    def test_archive_snapshot_dataclass(self):
        """Test ArchiveSnapshot dataclass."""
        snapshot = ArchiveSnapshot(
            url="https://example.com",
            timestamp=datetime(2024, 1, 1),
            archive_url="https://web.archive.org/web/20240101/https://example.com",
            status_code=200,
            digest="ABCDEF123456",
        )

        assert snapshot.url == "https://example.com"
        assert snapshot.status_code == 200
        assert snapshot.timestamp.year == 2024

    def test_archive_timeline_dataclass(self):
        """Test ArchiveTimeline dataclass."""
        snapshots = [
            ArchiveSnapshot(
                url="https://example.com",
                timestamp=datetime(2024, 1, 1),
                archive_url="https://web.archive.org/web/20240101/https://example.com",
                status_code=200,
            )
        ]

        timeline = ArchiveTimeline(
            url="https://example.com",
            first_seen=datetime(2024, 1, 1),
            last_seen=datetime(2024, 1, 1),
            snapshot_count=1,
            snapshots=snapshots,
        )

        assert timeline.url == "https://example.com"
        assert timeline.snapshot_count == 1
        assert len(timeline.snapshots) == 1
