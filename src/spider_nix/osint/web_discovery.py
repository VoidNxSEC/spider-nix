"""
Web discovery tools for advanced reconnaissance.

Provides GraphQL discovery, form analysis, directory bruteforcing,
and well-known resource scanning for comprehensive web intelligence.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class GraphQLEndpoint:
    """Discovered GraphQL endpoint with schema information."""

    url: str
    introspection_enabled: bool
    schema_available: bool = False
    types: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    mutations: list[str] = field(default_factory=list)
    directives: list[str] = field(default_factory=list)
    schema_json: dict | None = None
    confidence: float = 1.0


@dataclass
class FormField:
    """HTML form field information."""

    name: str
    field_type: str  # text, email, password, select, etc.
    required: bool = False
    placeholder: str | None = None
    options: list[str] = field(default_factory=list)
    validation_pattern: str | None = None


@dataclass
class FormAnalysis:
    """Analyzed HTML form with extracted intelligence."""

    url: str
    action: str
    method: str
    fields: list[FormField]
    has_captcha: bool = False
    has_file_upload: bool = False
    purpose: str | None = None  # contact, signup, login, search, etc.
    privacy_link: str | None = None
    terms_link: str | None = None
    field_count: int = 0
    complexity_score: float = 0.0


@dataclass
class DirectoryEntry:
    """Discovered directory or file path."""

    path: str
    status_code: int
    size_bytes: int
    discovered_via: str  # wordlist, bruteforce, sitemap
    content_type: str | None = None
    redirect_url: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WellKnownResource:
    """Well-known directory resource information."""

    path: str
    exists: bool
    resource_type: str  # security.txt, change-password, etc.
    content: str | None = None
    parsed_data: dict | None = None


# ============================================================================
# GraphQL Discovery
# ============================================================================


class GraphQLDiscovery:
    """
    Discover GraphQL endpoints and introspect schemas.

    Attempts to find GraphQL APIs by:
    - Testing common endpoint paths
    - Searching HTML for GraphQL references
    - Attempting schema introspection
    - Parsing and extracting type information
    """

    GRAPHQL_PATTERNS = [
        "/graphql",
        "/api/graphql",
        "/v1/graphql",
        "/v2/graphql",
        "/graphiql",
        "/playground",
        "/query",
        "/api/query",
    ]

    INTROSPECTION_QUERY = """
    query IntrospectionQuery {
      __schema {
        queryType { name }
        mutationType { name }
        subscriptionType { name }
        types {
          name
          kind
          description
        }
        directives {
          name
          description
        }
      }
    }
    """

    async def discover(self, base_url: str) -> list[GraphQLEndpoint]:
        """
        Discover GraphQL endpoints on target.

        Args:
            base_url: Base URL to scan

        Returns:
            List of discovered GraphQL endpoints
        """
        endpoints = []

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Try common paths
            for pattern in self.GRAPHQL_PATTERNS:
                url = urljoin(base_url, pattern)
                endpoint = await self._test_endpoint(client, url)
                if endpoint:
                    endpoints.append(endpoint)

            # Search HTML for GraphQL references
            try:
                response = await client.get(base_url)
                if response.status_code == 200:
                    html_endpoints = self._search_html_for_graphql(base_url, response.text)
                    for url in html_endpoints:
                        if url not in [e.url for e in endpoints]:
                            endpoint = await self._test_endpoint(client, url)
                            if endpoint:
                                endpoints.append(endpoint)
            except httpx.RequestError as e:
                logger.debug(f"Error fetching {base_url}: {e}")

        return endpoints

    async def _test_endpoint(self, client: httpx.AsyncClient, url: str) -> GraphQLEndpoint | None:
        """Test if URL is a GraphQL endpoint and attempt introspection."""
        try:
            # Try POST with introspection query
            response = await client.post(
                url,
                json={"query": self.INTROSPECTION_QUERY},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                try:
                    data = response.json()

                    # Check if it's a GraphQL response
                    if "data" in data or "errors" in data:
                        return self._parse_introspection_response(url, data)
                except json.JSONDecodeError:
                    pass

            # Try GET request (some endpoints support GET)
            response = await client.get(url)
            if response.status_code == 200:
                # Check for GraphQL-related content
                content_lower = response.text.lower()
                if any(keyword in content_lower for keyword in ["graphql", "graphiql", "playground"]):
                    return GraphQLEndpoint(
                        url=url,
                        introspection_enabled=False,
                        schema_available=False,
                        confidence=0.7,
                    )

        except httpx.RequestError as e:
            logger.debug(f"Error testing GraphQL endpoint {url}: {e}")

        return None

    def _parse_introspection_response(self, url: str, data: dict) -> GraphQLEndpoint:
        """Parse GraphQL introspection response."""
        endpoint = GraphQLEndpoint(
            url=url,
            introspection_enabled=False,
            schema_available=False,
        )

        if "errors" in data:
            # GraphQL endpoint found but introspection disabled
            error_messages = [e.get("message", "") for e in data["errors"]]
            if any("introspection" in msg.lower() for msg in error_messages):
                endpoint.introspection_enabled = False
                endpoint.confidence = 0.9
            return endpoint

        if "data" in data and "__schema" in data.get("data", {}):
            schema = data["data"]["__schema"]
            endpoint.introspection_enabled = True
            endpoint.schema_available = True
            endpoint.schema_json = schema

            # Extract types
            if "types" in schema:
                endpoint.types = [t["name"] for t in schema["types"] if not t["name"].startswith("__")]

            # Extract queries
            if "queryType" in schema and schema["queryType"]:
                query_type = schema["queryType"]["name"]
                endpoint.queries = [query_type]

            # Extract mutations
            if "mutationType" in schema and schema["mutationType"]:
                mutation_type = schema["mutationType"]["name"]
                endpoint.mutations = [mutation_type]

            # Extract directives
            if "directives" in schema:
                endpoint.directives = [d["name"] for d in schema["directives"]]

            endpoint.confidence = 1.0

        return endpoint

    def _search_html_for_graphql(self, base_url: str, html: str) -> list[str]:
        """Search HTML content for GraphQL endpoint references."""
        endpoints = set()

        # Search for GraphQL endpoint URLs in scripts
        patterns = [
            r'["\']([^"\']*(?:graphql|query)[^"\']*)["\']',
            r'endpoint["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'url["\']?\s*[:=]\s*["\']([^"\']*graphql[^"\']*)["\']',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                endpoint = match.group(1)
                if endpoint.startswith(("/", "http")):
                    full_url = urljoin(base_url, endpoint)
                    endpoints.add(full_url)

        return list(endpoints)


# ============================================================================
# Form Analyzer
# ============================================================================


class FormAnalyzer:
    """
    Discover and analyze HTML forms for competitive intelligence.

    Extracts form structure, field types, validation patterns,
    and infers purpose (login, contact, signup, etc.).
    """

    CAPTCHA_INDICATORS = [
        "recaptcha",
        "hcaptcha",
        "captcha",
        "cf-turnstile",
        "g-recaptcha",
        "h-captcha",
    ]

    PURPOSE_PATTERNS = {
        "login": ["password", "username", "email", "sign in", "log in"],
        "signup": ["sign up", "register", "create account", "password", "confirm"],
        "contact": ["message", "inquiry", "subject", "contact"],
        "search": ["search", "query", "q"],
        "newsletter": ["subscribe", "newsletter", "email"],
        "payment": ["card", "cvv", "billing", "payment"],
    }

    async def analyze_page(self, url: str, html: str) -> list[FormAnalysis]:
        """
        Extract and analyze all forms on a page.

        Args:
            url: Page URL
            html: HTML content

        Returns:
            List of analyzed forms
        """
        forms = []

        # Simple regex-based form extraction (can use BeautifulSoup for more robust parsing)
        form_pattern = r'<form[^>]*>(.*?)</form>'
        form_matches = re.finditer(form_pattern, html, re.IGNORECASE | re.DOTALL)

        for match in form_matches:
            form_html = match.group(0)
            form_analysis = self._analyze_form(url, form_html)
            if form_analysis:
                forms.append(form_analysis)

        return forms

    def _analyze_form(self, page_url: str, form_html: str) -> FormAnalysis | None:
        """Analyze a single form."""
        # Extract form attributes
        action_match = re.search(r'action=["\']([^"\']+)["\']', form_html, re.IGNORECASE)
        method_match = re.search(r'method=["\']([^"\']+)["\']', form_html, re.IGNORECASE)

        action = action_match.group(1) if action_match else ""
        method = method_match.group(1).upper() if method_match else "GET"

        # Convert relative action to absolute URL
        if action:
            action = urljoin(page_url, action)
        else:
            action = page_url

        # Extract fields
        fields = self._extract_fields(form_html)

        if not fields:
            return None

        # Detect CAPTCHA
        has_captcha = any(
            indicator in form_html.lower() for indicator in self.CAPTCHA_INDICATORS
        )

        # Detect file upload
        has_file_upload = 'type="file"' in form_html.lower()

        # Detect purpose
        purpose = self._detect_purpose(fields, form_html, action)

        # Extract privacy/terms links
        privacy_link = self._extract_link(form_html, ["privacy", "policy"])
        terms_link = self._extract_link(form_html, ["terms", "conditions"])

        # Calculate complexity score
        complexity_score = self._calculate_complexity(fields, has_captcha, has_file_upload)

        return FormAnalysis(
            url=page_url,
            action=action,
            method=method,
            fields=fields,
            has_captcha=has_captcha,
            has_file_upload=has_file_upload,
            purpose=purpose,
            privacy_link=privacy_link,
            terms_link=terms_link,
            field_count=len(fields),
            complexity_score=complexity_score,
        )

    def _extract_fields(self, form_html: str) -> list[FormField]:
        """Extract form fields."""
        fields = []

        # Extract input fields
        input_pattern = r'<input[^>]*>'
        for match in re.finditer(input_pattern, form_html, re.IGNORECASE):
            input_html = match.group(0)

            name_match = re.search(r'name=["\']([^"\']+)["\']', input_html)
            type_match = re.search(r'type=["\']([^"\']+)["\']', input_html)
            required = 'required' in input_html.lower()
            placeholder_match = re.search(r'placeholder=["\']([^"\']+)["\']', input_html)
            pattern_match = re.search(r'pattern=["\']([^"\']+)["\']', input_html)

            if name_match:
                field = FormField(
                    name=name_match.group(1),
                    field_type=type_match.group(1) if type_match else "text",
                    required=required,
                    placeholder=placeholder_match.group(1) if placeholder_match else None,
                    validation_pattern=pattern_match.group(1) if pattern_match else None,
                )
                fields.append(field)

        # Extract textarea fields
        textarea_pattern = r'<textarea[^>]*>(.*?)</textarea>'
        for match in re.finditer(textarea_pattern, form_html, re.IGNORECASE | re.DOTALL):
            textarea_html = match.group(0)
            name_match = re.search(r'name=["\']([^"\']+)["\']', textarea_html)
            required = 'required' in textarea_html.lower()

            if name_match:
                field = FormField(
                    name=name_match.group(1),
                    field_type="textarea",
                    required=required,
                )
                fields.append(field)

        # Extract select fields
        select_pattern = r'<select[^>]*>(.*?)</select>'
        for match in re.finditer(select_pattern, form_html, re.IGNORECASE | re.DOTALL):
            select_html = match.group(0)
            name_match = re.search(r'name=["\']([^"\']+)["\']', select_html)
            required = 'required' in select_html.lower()

            # Extract options
            options = re.findall(r'<option[^>]*>([^<]+)</option>', select_html, re.IGNORECASE)

            if name_match:
                field = FormField(
                    name=name_match.group(1),
                    field_type="select",
                    required=required,
                    options=options,
                )
                fields.append(field)

        return fields

    def _detect_purpose(self, fields: list[FormField], form_html: str, action: str) -> str | None:
        """Heuristically detect form purpose."""
        field_names = {f.name.lower() for f in fields}
        combined_text = " ".join(field_names) + " " + form_html.lower() + " " + action.lower()

        # Score each purpose
        scores = {}
        for purpose, keywords in self.PURPOSE_PATTERNS.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            if score > 0:
                scores[purpose] = score

        if scores:
            return max(scores, key=scores.get)

        return None

    def _extract_link(self, form_html: str, keywords: list[str]) -> str | None:
        """Extract link matching keywords."""
        link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
        for match in re.finditer(link_pattern, form_html, re.IGNORECASE):
            href = match.group(1)
            text = match.group(2).lower()

            if any(keyword in text for keyword in keywords):
                return href

        return None

    def _calculate_complexity(self, fields: list[FormField], has_captcha: bool, has_file_upload: bool) -> float:
        """Calculate form complexity score (0.0 to 1.0)."""
        score = 0.0

        # Base score from field count
        score += min(len(fields) / 10.0, 0.5)

        # Required fields add complexity
        required_count = sum(1 for f in fields if f.required)
        score += min(required_count / 5.0, 0.2)

        # Validation patterns add complexity
        pattern_count = sum(1 for f in fields if f.validation_pattern)
        score += min(pattern_count / 3.0, 0.1)

        # CAPTCHA adds complexity
        if has_captcha:
            score += 0.1

        # File upload adds complexity
        if has_file_upload:
            score += 0.1

        return min(score, 1.0)


# ============================================================================
# Directory Brute-forcer
# ============================================================================


class DirectoryBruteforcer:
    """
    Brute-force directory and file discovery.

    Uses wordlists to discover hidden directories, files, and API endpoints
    with configurable concurrency and extension support.
    """

    DEFAULT_WORDLIST = [
        "admin", "api", "backup", "config", "dashboard",
        "dev", "docs", "download", "files", "images",
        "login", "portal", "private", "public", "static",
        "test", "tmp", "upload", "user", "v1", "v2",
        "assets", "cache", "data", "db", "logs",
        "src", "vendor", "wp-admin", "wp-content",
    ]

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize brute-forcer.

        Args:
            max_concurrent: Maximum concurrent requests
        """
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def bruteforce(
        self,
        base_url: str,
        wordlist: list[str] | None = None,
        extensions: list[str] | None = None,
    ) -> list[DirectoryEntry]:
        """
        Brute-force directories and files.

        Args:
            base_url: Base URL to scan
            wordlist: Custom wordlist (uses default if None)
            extensions: File extensions to try (e.g., ["php", "html"])

        Returns:
            List of discovered entries
        """
        wordlist = wordlist or self.DEFAULT_WORDLIST
        extensions = extensions or []

        # Build list of paths to test
        paths_to_test = []

        for word in wordlist:
            # Test as directory
            paths_to_test.append(f"/{word}")
            paths_to_test.append(f"/{word}/")

            # Test with extensions
            for ext in extensions:
                paths_to_test.append(f"/{word}.{ext}")

        # Test all paths concurrently
        results = []
        tasks = [self._test_path(base_url, path) for path in paths_to_test]

        for coro in asyncio.as_completed(tasks):
            entry = await coro
            if entry:
                results.append(entry)

        return results

    async def _test_path(self, base_url: str, path: str) -> DirectoryEntry | None:
        """Test a single path."""
        url = urljoin(base_url, path)

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                    response = await client.get(url)

                    # Only track interesting status codes
                    if response.status_code in {200, 301, 302, 403}:
                        content_type = response.headers.get("Content-Type")
                        redirect = response.headers.get("Location")

                        return DirectoryEntry(
                            path=path,
                            status_code=response.status_code,
                            size_bytes=len(response.content),
                            content_type=content_type,
                            redirect_url=redirect,
                            discovered_via="wordlist",
                        )

            except httpx.RequestError:
                pass

        return None


# ============================================================================
# Well-known Scanner
# ============================================================================


class WellKnownScanner:
    """
    Scan .well-known directory for standard resources.

    Discovers security.txt, change-password URLs, and other
    standard well-known resources as defined by RFC 8615.
    """

    WELL_KNOWN_PATHS = [
        "security.txt",
        "change-password",
        "matrix/server",
        "apple-app-site-association",
        "assetlinks.json",
        "dnt-policy.txt",
        "openid-configuration",
        "webfinger",
        "host-meta",
        "host-meta.json",
        "nodeinfo",
        "oauth-authorization-server",
    ]

    async def scan(
        self,
        base_url: str,
        resources: list[str] | None = None,
    ) -> list[WellKnownResource]:
        """
        Scan for .well-known resources.

        Args:
            base_url: Base URL to scan
            resources: Specific resources to check (uses all if None)

        Returns:
            List of found resources
        """
        resources_to_check = resources or self.WELL_KNOWN_PATHS
        found_resources = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for resource in resources_to_check:
                url = urljoin(base_url, f"/.well-known/{resource}")

                try:
                    response = await client.get(url)

                    if response.status_code == 200:
                        content = response.text
                        parsed_data = None

                        # Try to parse JSON resources
                        if resource.endswith(".json") or "json" in response.headers.get("Content-Type", ""):
                            try:
                                parsed_data = response.json()
                            except json.JSONDecodeError:
                                pass

                        found_resources.append(
                            WellKnownResource(
                                path=f"/.well-known/{resource}",
                                exists=True,
                                content=content[:1000],  # Truncate to 1000 chars
                                parsed_data=parsed_data,
                                resource_type=resource,
                            )
                        )

                except httpx.RequestError:
                    pass

        return found_resources


# ============================================================================
# Utility Functions
# ============================================================================


def load_wordlist(name: str) -> list[str]:
    """
    Load built-in wordlist from wordlists directory.

    Args:
        name: Wordlist name (without .txt extension)

    Returns:
        List of words, or empty list if file not found
    """
    wordlist_dir = Path(__file__).parent / "wordlists"
    path = wordlist_dir / f"{name}.txt"

    if not path.exists():
        logger.warning(f"Wordlist {name}.txt not found at {wordlist_dir}")
        return []

    try:
        return path.read_text().strip().splitlines()
    except Exception as e:
        logger.error(f"Error reading wordlist {name}: {e}")
        return []
