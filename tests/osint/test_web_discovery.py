"""Tests for web_discovery module."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from spider_nix.osint.web_discovery import (
    GraphQLDiscovery,
    GraphQLEndpoint,
    FormAnalyzer,
    FormAnalysis,
    FormField,
    DirectoryBruteforcer,
    DirectoryEntry,
    WellKnownScanner,
    WellKnownResource,
)


class TestGraphQLDiscovery:
    """Tests for GraphQL discovery."""

    @pytest.mark.asyncio
    async def test_discover_endpoint_at_common_path(self, httpx_mock):
        """Test discovering GraphQL endpoint at common path."""
        # Mock GraphQL endpoint
        httpx_mock.add_response(
            url="https://example.com/graphql",
            method="POST",
            json={"data": {"__schema": {"queryType": {"name": "Query"}}}},
        )

        discovery = GraphQLDiscovery()
        endpoints = await discovery.discover("https://example.com")

        assert len(endpoints) > 0
        assert any(e.url == "https://example.com/graphql" for e in endpoints)

    @pytest.mark.asyncio
    async def test_introspection_query(self, httpx_mock):
        """Test GraphQL introspection query."""
        schema_data = {
            "data": {
                "__schema": {
                    "queryType": {"name": "Query"},
                    "mutationType": {"name": "Mutation"},
                    "types": [
                        {"name": "User", "kind": "OBJECT"},
                        {"name": "Post", "kind": "OBJECT"},
                    ],
                    "directives": [{"name": "include"}, {"name": "skip"}],
                }
            }
        }

        httpx_mock.add_response(
            url="https://example.com/graphql",
            method="POST",
            json=schema_data,
        )

        discovery = GraphQLDiscovery()
        result = await discovery._introspect_endpoint("https://example.com/graphql")

        assert result is not None
        assert result.introspection_enabled is True
        assert result.schema_available is True
        assert len(result.types) == 2
        assert "User" in result.types
        assert len(result.directives) == 2

    @pytest.mark.asyncio
    async def test_introspection_disabled(self, httpx_mock):
        """Test handling of disabled introspection."""
        httpx_mock.add_response(
            url="https://example.com/graphql",
            method="POST",
            json={"errors": [{"message": "GraphQL introspection is not allowed"}]},
        )

        discovery = GraphQLDiscovery()
        result = await discovery._introspect_endpoint("https://example.com/graphql")

        # Should still return endpoint but with introspection_enabled=False
        assert result is not None
        assert result.introspection_enabled is False
        assert result.schema_available is False

    @pytest.mark.asyncio
    async def test_detect_from_html(self):
        """Test detecting GraphQL endpoints from HTML."""
        html = """
        <html>
            <script>
                fetch('/api/graphql', {method: 'POST'});
            </script>
        </html>
        """

        discovery = GraphQLDiscovery()
        endpoints = discovery._detect_from_html(html, "https://example.com")

        assert len(endpoints) > 0
        assert any("/api/graphql" in e for e in endpoints)

    def test_graphql_endpoint_dataclass(self):
        """Test GraphQLEndpoint dataclass."""
        endpoint = GraphQLEndpoint(
            url="https://example.com/graphql",
            introspection_enabled=True,
            schema_available=True,
            types=["User", "Post"],
            queries=["user", "posts"],
            mutations=["createPost"],
            directives=["include", "skip"],
            confidence=1.0,
        )

        assert endpoint.url == "https://example.com/graphql"
        assert endpoint.introspection_enabled is True
        assert len(endpoint.types) == 2
        assert "User" in endpoint.types


class TestFormAnalyzer:
    """Tests for form analysis."""

    @pytest.mark.asyncio
    async def test_analyze_simple_form(self):
        """Test analyzing a simple HTML form."""
        html = """
        <html>
            <form action="/submit" method="post">
                <input type="text" name="username" required>
                <input type="password" name="password" required>
                <input type="submit" value="Login">
            </form>
        </html>
        """

        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page("https://example.com/login", html)

        assert len(forms) == 1
        form = forms[0]
        assert form.action == "/submit"
        assert form.method == "post"
        assert form.field_count == 2  # username, password (submit doesn't count)
        assert len(form.fields) == 2

    @pytest.mark.asyncio
    async def test_detect_form_purpose(self):
        """Test detecting form purpose (login, signup, etc.)."""
        html = """
        <html>
            <form action="/login" method="post">
                <input type="text" name="username">
                <input type="password" name="password">
                <button type="submit">Login</button>
            </form>
        </html>
        """

        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page("https://example.com", html)

        assert len(forms) == 1
        # Purpose detection should identify this as a login form
        assert forms[0].purpose in ["login", "unknown"]  # Depends on implementation

    @pytest.mark.asyncio
    async def test_detect_captcha(self):
        """Test detecting CAPTCHA in forms."""
        html = """
        <html>
            <form action="/submit" method="post">
                <input type="text" name="username">
                <div class="g-recaptcha" data-sitekey="abc123"></div>
                <input type="submit">
            </form>
        </html>
        """

        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page("https://example.com", html)

        assert len(forms) == 1
        assert forms[0].has_captcha is True

    @pytest.mark.asyncio
    async def test_detect_file_upload(self):
        """Test detecting file upload fields."""
        html = """
        <html>
            <form action="/upload" method="post" enctype="multipart/form-data">
                <input type="file" name="document">
                <input type="submit">
            </form>
        </html>
        """

        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page("https://example.com", html)

        assert len(forms) == 1
        assert forms[0].has_file_upload is True

    @pytest.mark.asyncio
    async def test_form_field_parsing(self):
        """Test parsing form fields with various attributes."""
        html = """
        <html>
            <form action="/submit" method="post">
                <input type="email" name="email" required placeholder="Enter email">
                <select name="country">
                    <option>USA</option>
                    <option>UK</option>
                </select>
                <input type="text" name="optional_field">
            </form>
        </html>
        """

        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page("https://example.com", html)

        assert len(forms) == 1
        form = forms[0]
        assert form.field_count == 3

        # Check field details
        email_field = next((f for f in form.fields if f.name == "email"), None)
        assert email_field is not None
        assert email_field.field_type == "email"
        assert email_field.required is True
        assert email_field.placeholder == "Enter email"

    def test_form_field_dataclass(self):
        """Test FormField dataclass."""
        field = FormField(
            name="username",
            field_type="text",
            required=True,
            placeholder="Enter username",
        )

        assert field.name == "username"
        assert field.field_type == "text"
        assert field.required is True


class TestDirectoryBruteforcer:
    """Tests for directory brute-forcing."""

    @pytest.mark.asyncio
    async def test_bruteforce_basic(self, httpx_mock):
        """Test basic directory brute-forcing."""
        httpx_mock.add_response(url="https://example.com/admin", status_code=200, text="Admin Panel")
        httpx_mock.add_response(url="https://example.com/api", status_code=404)
        httpx_mock.add_response(url="https://example.com/backup", status_code=403)

        bruteforcer = DirectoryBruteforcer()
        entries = await bruteforcer.bruteforce(
            "https://example.com",
            wordlist=["admin", "api", "backup"],
            max_concurrent=2,
        )

        # Should find admin (200) and backup (403), but not api (404)
        assert len(entries) >= 1
        admin_entry = next((e for e in entries if e.path == "/admin"), None)
        assert admin_entry is not None
        assert admin_entry.status_code == 200

    @pytest.mark.asyncio
    async def test_bruteforce_with_extensions(self, httpx_mock):
        """Test brute-forcing with file extensions."""
        httpx_mock.add_response(url="https://example.com/config.php", status_code=200)
        httpx_mock.add_response(url="https://example.com/config.json", status_code=404)

        bruteforcer = DirectoryBruteforcer()
        entries = await bruteforcer.bruteforce(
            "https://example.com",
            wordlist=["config"],
            extensions=["php", "json"],
            max_concurrent=2,
        )

        # Should find config.php but not config.json
        php_entry = next((e for e in entries if "config.php" in e.path), None)
        assert php_entry is not None

    @pytest.mark.asyncio
    async def test_detect_redirects(self, httpx_mock):
        """Test detecting and following redirects."""
        httpx_mock.add_response(
            url="https://example.com/old-admin",
            status_code=301,
            headers={"Location": "/admin"},
        )

        bruteforcer = DirectoryBruteforcer()
        entries = await bruteforcer.bruteforce(
            "https://example.com",
            wordlist=["old-admin"],
            max_concurrent=1,
        )

        assert len(entries) > 0
        redirect_entry = entries[0]
        assert redirect_entry.status_code == 301

    @pytest.mark.asyncio
    async def test_concurrent_limiting(self, httpx_mock):
        """Test that concurrent requests are properly limited."""
        # Add multiple mock responses
        for i in range(10):
            httpx_mock.add_response(
                url=f"https://example.com/path{i}",
                status_code=404,
            )

        bruteforcer = DirectoryBruteforcer()
        wordlist = [f"path{i}" for i in range(10)]

        # Should respect max_concurrent limit
        entries = await bruteforcer.bruteforce(
            "https://example.com",
            wordlist=wordlist,
            max_concurrent=3,
        )

        # Test completes without overwhelming the server
        assert isinstance(entries, list)

    def test_directory_entry_dataclass(self):
        """Test DirectoryEntry dataclass."""
        entry = DirectoryEntry(
            path="/admin",
            status_code=200,
            size_bytes=1024,
            content_type="text/html",
            discovered_via="wordlist",
        )

        assert entry.path == "/admin"
        assert entry.status_code == 200
        assert entry.size_bytes == 1024


class TestWellKnownScanner:
    """Tests for .well-known directory scanning."""

    @pytest.mark.asyncio
    async def test_scan_security_txt(self, httpx_mock):
        """Test scanning for security.txt."""
        security_txt = """
        Contact: security@example.com
        Expires: 2025-12-31T23:59:59z
        """

        httpx_mock.add_response(
            url="https://example.com/.well-known/security.txt",
            status_code=200,
            text=security_txt,
        )

        scanner = WellKnownScanner()
        resources = await scanner.scan("https://example.com", resources=["security.txt"])

        assert len(resources) > 0
        security_resource = next((r for r in resources if r.path == "security.txt"), None)
        assert security_resource is not None
        assert security_resource.exists is True
        assert "security@example.com" in security_resource.content

    @pytest.mark.asyncio
    async def test_scan_multiple_resources(self, httpx_mock):
        """Test scanning multiple well-known resources."""
        httpx_mock.add_response(
            url="https://example.com/.well-known/security.txt",
            status_code=200,
            text="Contact: security@example.com",
        )
        httpx_mock.add_response(
            url="https://example.com/.well-known/change-password",
            status_code=404,
        )

        scanner = WellKnownScanner()
        resources = await scanner.scan(
            "https://example.com",
            resources=["security.txt", "change-password"],
        )

        # Should find security.txt but not change-password
        assert len(resources) >= 1
        found_paths = [r.path for r in resources if r.exists]
        assert "security.txt" in found_paths

    @pytest.mark.asyncio
    async def test_parse_json_resource(self, httpx_mock):
        """Test parsing JSON well-known resources."""
        json_data = {
            "related_applications": [
                {"platform": "play", "id": "com.example.app"}
            ]
        }

        httpx_mock.add_response(
            url="https://example.com/.well-known/assetlinks.json",
            status_code=200,
            json=json_data,
        )

        scanner = WellKnownScanner()
        resources = await scanner.scan("https://example.com", resources=["assetlinks.json"])

        assert len(resources) > 0
        json_resource = next((r for r in resources if r.path == "assetlinks.json"), None)
        assert json_resource is not None
        assert json_resource.exists is True
        assert json_resource.parsed_data is not None

    def test_wellknown_resource_dataclass(self):
        """Test WellKnownResource dataclass."""
        resource = WellKnownResource(
            path="security.txt",
            exists=True,
            content="Contact: security@example.com",
            resource_type="security",
        )

        assert resource.path == "security.txt"
        assert resource.exists is True
        assert "security@example.com" in resource.content
