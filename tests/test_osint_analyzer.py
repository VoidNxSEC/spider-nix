"""Tests for OSINT content analyzer module."""

import pytest

from spider_nix.osint.analyzer import (
    ContentAnalyzer,
    TechnologyDetector,
    ContactHarvester,
    APIDiscovery,
)


class TestTechnologyDetector:
    """Test technology detection."""

    def test_detect_jquery(self):
        """Test jQuery detection."""
        detector = TechnologyDetector()
        html = '<script src="https://code.jquery.com/jquery.min.js"></script>'

        techs = detector.detect(html)

        jquery = [t for t in techs if t.name == "jQuery"]
        assert len(jquery) >= 1
        assert jquery[0].category == "library"

    def test_detect_react(self):
        """Test React detection."""
        detector = TechnologyDetector()
        html = '<div data-reactroot><script src="/static/js/react.min.js"></script></div>'

        techs = detector.detect(html)

        react = [t for t in techs if t.name == "React"]
        assert len(react) == 1
        assert react[0].category == "framework"

    def test_detect_wordpress(self):
        """Test WordPress detection."""
        detector = TechnologyDetector()
        html = '''
        <link rel="stylesheet" href="/wp-content/themes/twentytwenty/style.css">
        <script src="/wp-includes/js/jquery/jquery.min.js"></script>
        '''

        techs = detector.detect(html)

        wordpress = [t for t in techs if t.name == "WordPress"]
        assert len(wordpress) == 1
        assert wordpress[0].category == "cms"

    def test_detect_google_analytics(self):
        """Test Google Analytics detection."""
        detector = TechnologyDetector()
        html = '<script src="https://www.google-analytics.com/analytics.js"></script>'

        techs = detector.detect(html)

        ga = [t for t in techs if t.name == "Google Analytics"]
        assert len(ga) == 1
        assert ga[0].category == "analytics"

    def test_detect_from_headers(self):
        """Test detection from HTTP headers."""
        detector = TechnologyDetector()
        headers = {
            "Server": "nginx/1.20.0",
            "CF-Ray": "12345-LAX",
        }

        techs = detector.detect("", headers)

        assert len(techs) >= 2
        nginx = [t for t in techs if t.name == "Nginx"]
        cloudflare = [t for t in techs if t.name == "Cloudflare"]

        assert len(nginx) == 1
        assert len(cloudflare) == 1

    def test_detect_multiple_techs(self):
        """Test detection of multiple technologies."""
        detector = TechnologyDetector()
        html = '''
        <script src="https://code.jquery.com/jquery.min.js"></script>
        <script src="https://www.google-analytics.com/analytics.js"></script>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.0.0/dist/css/bootstrap.min.css">
        '''

        techs = detector.detect(html)

        assert len(techs) >= 2
        tech_names = {t.name for t in techs}
        # Should detect at least GA and Bootstrap
        assert "Google Analytics" in tech_names or "Bootstrap" in tech_names


class TestContactHarvester:
    """Test contact information harvesting."""

    def test_extract_emails(self):
        """Test email extraction."""
        harvester = ContactHarvester()
        html = "Contact: john@example.com and support@test.org"

        contacts = harvester.extract_emails(html)

        assert len(contacts) == 2
        emails = {c.value for c in contacts}
        assert "john@example.com" in emails
        assert "support@test.org" in emails

    def test_extract_phones(self):
        """Test phone number extraction."""
        harvester = ContactHarvester()
        html = "Call us: +1-555-123-4567 or (555) 987-6543"

        contacts = harvester.extract_phones(html)

        assert len(contacts) >= 1
        # At least one phone should be detected

    def test_extract_social_media(self):
        """Test social media profile extraction."""
        harvester = ContactHarvester()
        html = '''
        Follow us:
        <a href="https://twitter.com/example">Twitter</a>
        <a href="https://github.com/testuser">GitHub</a>
        <a href="https://linkedin.com/in/johndoe">LinkedIn</a>
        '''

        contacts = harvester.extract_social_media(html)

        assert len(contacts) == 3
        platforms = {c.context for c in contacts}
        assert "twitter" in platforms
        assert "github" in platforms
        assert "linkedin" in platforms

    def test_harvest_all(self):
        """Test harvesting all contact types."""
        harvester = ContactHarvester()
        html = '''
        Contact: admin@example.com
        Phone: +1-555-1234
        Twitter: https://twitter.com/company
        '''

        contacts = harvester.harvest(html)

        assert len(contacts) >= 2  # At least email and social
        types = {c.type for c in contacts}
        assert "email" in types


class TestAPIDiscovery:
    """Test API endpoint discovery."""

    def test_discover_fetch_calls(self):
        """Test discovery from fetch() calls."""
        discovery = APIDiscovery()
        html = '''
        <script>
        fetch('/api/v1/users')
        fetch('/api/v2/products')
        </script>
        '''

        endpoints = discovery.discover(html, "https://example.com")

        assert len(endpoints) >= 2
        paths = {e.path for e in endpoints}
        assert "/api/v1/users" in paths
        assert "/api/v2/products" in paths

    def test_discover_axios_calls(self):
        """Test discovery from axios calls."""
        discovery = APIDiscovery()
        html = '''
        <script>
        axios.get('/api/data')
        axios.post('/api/submit')
        </script>
        '''

        endpoints = discovery.discover(html, "https://example.com")

        assert len(endpoints) >= 2
        paths = {e.path for e in endpoints}
        assert "/api/data" in paths
        assert "/api/submit" in paths

    def test_discover_absolute_urls(self):
        """Test discovery of absolute URLs."""
        discovery = APIDiscovery()
        html = '''
        <script>
        fetch('https://api.example.com/v1/users')
        </script>
        '''

        endpoints = discovery.discover(html, "https://example.com")

        assert len(endpoints) >= 1
        assert any("api.example.com" in e.url for e in endpoints)

    def test_discover_graphql(self):
        """Test GraphQL endpoint discovery."""
        discovery = APIDiscovery()
        html = '<script>fetch("/graphql")</script>'

        endpoints = discovery.discover(html, "https://example.com")

        assert len(endpoints) >= 1
        assert any("graphql" in e.path for e in endpoints)


class TestContentAnalyzer:
    """Test complete content analyzer."""

    def test_analyze_complete(self):
        """Test complete content analysis."""
        analyzer = ContentAnalyzer()
        html = '''
        <html>
        <head><title>Test Page</title></head>
        <body>
        <script src="https://code.jquery.com/jquery.min.js"></script>
        <script>fetch('/api/v1/users')</script>
        Contact: admin@example.com
        Twitter: https://twitter.com/company
        </body>
        </html>
        '''

        result = analyzer.analyze("https://example.com", html, {"server": "nginx"})

        # Should detect technologies
        assert len(result.tech_stack) >= 2
        tech_names = {t.name for t in result.tech_stack}
        assert "jQuery" in tech_names
        assert "Nginx" in tech_names

        # Should find contacts
        assert len(result.contacts) >= 2

        # Should find API endpoints
        assert len(result.api_endpoints) >= 1

        # Should have metadata
        assert result.metadata["title"] == "Test Page"
        assert result.metadata["tech_count"] >= 2

    def test_extract_title(self):
        """Test title extraction."""
        analyzer = ContentAnalyzer()
        html = "<html><head><title>My Test Page</title></head></html>"

        title = analyzer._extract_title(html)

        assert title == "My Test Page"

    def test_extract_meta_description(self):
        """Test meta description extraction."""
        analyzer = ContentAnalyzer()
        html = '<meta name="description" content="This is a test description">'

        description = analyzer._extract_meta_description(html)

        assert description == "This is a test description"
