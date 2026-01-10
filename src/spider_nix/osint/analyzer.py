"""
Content analysis module for OSINT data extraction.

Provides technology detection, email/phone harvesting, API endpoint discovery,
and metadata extraction from crawled content.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


@dataclass
class TechStack:
    """Detected technology information."""

    name: str
    category: str  # framework, cms, analytics, cdn, server, etc
    version: str | None = None
    confidence: float = 1.0  # 0.0 to 1.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class Contact:
    """Extracted contact information."""

    type: str  # email, phone, social
    value: str
    context: str | None = None  # surrounding text


@dataclass
class APIEndpoint:
    """Discovered API endpoint."""

    url: str
    method: str  # GET, POST, etc
    path: str
    parameters: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Combined analysis result."""

    url: str
    tech_stack: list[TechStack] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    api_endpoints: list[APIEndpoint] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class TechnologyDetector:
    """
    Detect web technologies from HTML/headers/scripts.

    Similar to Wappalyzer - identifies frameworks, CMS, analytics, CDNs, etc.
    """

    # Technology signatures (regex patterns and header checks)
    SIGNATURES = {
        # Frameworks
        "React": {
            "category": "framework",
            "patterns": [
                r'react\.(?:min\.)?js',
                r'data-reactroot',
                r'__REACT_DEVTOOLS',
            ],
        },
        "Vue.js": {
            "category": "framework",
            "patterns": [
                r'vue\.(?:min\.)?js',
                r'data-v-[a-f0-9]{8}',
                r'__VUE__',
            ],
        },
        "Angular": {
            "category": "framework",
            "patterns": [
                r'angular\.(?:min\.)?js',
                r'ng-app',
                r'ng-controller',
            ],
        },
        "Next.js": {
            "category": "framework",
            "patterns": [
                r'/_next/static/',
                r'__NEXT_DATA__',
            ],
        },
        "Nuxt.js": {
            "category": "framework",
            "patterns": [
                r'/_nuxt/',
                r'__NUXT__',
            ],
        },
        # CMS
        "WordPress": {
            "category": "cms",
            "patterns": [
                r'/wp-content/',
                r'/wp-includes/',
                r'wp-json',
            ],
        },
        "Drupal": {
            "category": "cms",
            "patterns": [
                r'/sites/default/',
                r'Drupal\.settings',
                r'/misc/drupal\.js',
            ],
        },
        "Joomla": {
            "category": "cms",
            "patterns": [
                r'/components/com_',
                r'/media/jui/',
                r'joomla',
            ],
        },
        # Analytics
        "Google Analytics": {
            "category": "analytics",
            "patterns": [
                r'google-analytics\.com/analytics\.js',
                r'googletagmanager\.com/gtag',
                r'ga\(\'create\'',
            ],
        },
        "Google Tag Manager": {
            "category": "analytics",
            "patterns": [
                r'googletagmanager\.com/gtm\.js',
                r'dataLayer',
            ],
        },
        # CDN
        "Cloudflare": {
            "category": "cdn",
            "patterns": [
                r'cloudflare',
            ],
            "headers": ["cf-ray", "cf-cache-status"],
        },
        "Fastly": {
            "category": "cdn",
            "headers": ["fastly-"],
        },
        # Web Servers
        "Nginx": {
            "category": "server",
            "headers": ["nginx"],
        },
        "Apache": {
            "category": "server",
            "headers": ["apache"],
        },
        # JavaScript Libraries
        "jQuery": {
            "category": "library",
            "patterns": [
                r'jquery\.(?:min\.)?js',
                r'jQuery\.fn\.jquery',
            ],
        },
        "Bootstrap": {
            "category": "library",
            "patterns": [
                r'bootstrap\.(?:min\.)?css',
                r'bootstrap\.(?:min\.)?js',
            ],
        },
    }

    def detect(self, html: str, headers: dict[str, str] | None = None) -> list[TechStack]:
        """
        Detect technologies from HTML content and HTTP headers.

        Args:
            html: HTML content
            headers: HTTP response headers

        Returns:
            List of detected technologies
        """
        detected = []
        headers = headers or {}

        # Normalize headers to lowercase
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}

        for tech_name, signature in self.SIGNATURES.items():
            evidence = []

            # Check patterns in HTML
            if "patterns" in signature:
                for pattern in signature["patterns"]:
                    if re.search(pattern, html, re.IGNORECASE):
                        evidence.append(f"Pattern matched: {pattern}")

            # Check headers
            if "headers" in signature:
                for header_pattern in signature["headers"]:
                    for header_key, header_value in headers_lower.items():
                        if header_pattern in header_key or header_pattern in header_value:
                            evidence.append(f"Header matched: {header_key}")

            if evidence:
                detected.append(
                    TechStack(
                        name=tech_name,
                        category=signature["category"],
                        evidence=evidence,
                        confidence=min(1.0, len(evidence) * 0.3),
                    )
                )

        return detected


class ContactHarvester:
    """Extract contact information (emails, phones, social media) from content."""

    # Regex patterns
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    # Phone patterns (US, international)
    PHONE_PATTERNS = [
        r'\+?1?\s?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}',  # US
        r'\+\d{1,3}\s?\d{1,4}\s?\d{1,4}\s?\d{1,9}',      # International
    ]

    # Social media patterns
    SOCIAL_PATTERNS = {
        "twitter": r'(?:twitter\.com|x\.com)/([A-Za-z0-9_]{1,15})',
        "linkedin": r'linkedin\.com/in/([A-Za-z0-9_-]+)',
        "github": r'github\.com/([A-Za-z0-9_-]+)',
        "facebook": r'facebook\.com/([A-Za-z0-9._-]+)',
        "instagram": r'instagram\.com/([A-Za-z0-9._]+)',
    }

    def extract_emails(self, html: str) -> list[Contact]:
        """Extract email addresses."""
        emails = set(re.findall(self.EMAIL_PATTERN, html))
        return [Contact(type="email", value=email) for email in emails]

    def extract_phones(self, html: str) -> list[Contact]:
        """Extract phone numbers."""
        phones = set()
        for pattern in self.PHONE_PATTERNS:
            phones.update(re.findall(pattern, html))

        return [Contact(type="phone", value=phone) for phone in phones]

    def extract_social_media(self, html: str) -> list[Contact]:
        """Extract social media profiles."""
        contacts = []

        for platform, pattern in self.SOCIAL_PATTERNS.items():
            matches = re.findall(pattern, html, re.IGNORECASE)
            for username in set(matches):
                contacts.append(
                    Contact(
                        type="social",
                        value=f"{platform}:{username}",
                        context=platform,
                    )
                )

        return contacts

    def harvest(self, html: str) -> list[Contact]:
        """Extract all contact information."""
        contacts = []
        contacts.extend(self.extract_emails(html))
        contacts.extend(self.extract_phones(html))
        contacts.extend(self.extract_social_media(html))
        return contacts


class APIDiscovery:
    """Discover API endpoints from JavaScript files and HTML."""

    # Patterns for API endpoints
    API_PATTERNS = [
        # Fetch/axios calls
        r'fetch\([\'"]([^\'"]+)[\'"]',
        r'axios\.(?:get|post|put|delete)\([\'"]([^\'"]+)[\'"]',

        # jQuery ajax
        r'\$\.ajax\({[^}]*url:\s*[\'"]([^\'"]+)[\'"]',

        # Direct URLs in JS
        r'[\'"]/(api|v\d+|graphql|rest)/[^\'"]+[\'"]',

        # Common API paths
        r'[\'"]https?://[^\'"]+/(?:api|v\d+|graphql|rest)/[^\'"]+[\'"]',
    ]

    def discover(self, html: str, base_url: str) -> list[APIEndpoint]:
        """
        Discover API endpoints from HTML/JS content.

        Args:
            html: HTML/JS content
            base_url: Base URL for resolving relative paths

        Returns:
            List of discovered API endpoints
        """
        endpoints = set()

        for pattern in self.API_PATTERNS:
            matches = re.findall(pattern, html, re.IGNORECASE)
            endpoints.update(matches)

        api_endpoints = []
        for endpoint in endpoints:
            # Normalize endpoint
            if not endpoint.startswith('http'):
                endpoint = urljoin(base_url, endpoint)

            parsed = urlparse(endpoint)

            # Extract path and potential parameters
            path = parsed.path
            params = []

            # Look for template variables
            template_vars = re.findall(r'\{(\w+)\}', path)
            params.extend(template_vars)

            # Look for :param style
            colon_vars = re.findall(r':(\w+)', path)
            params.extend(colon_vars)

            api_endpoints.append(
                APIEndpoint(
                    url=endpoint,
                    method="GET",  # Default, could be enhanced
                    path=path,
                    parameters=params,
                )
            )

        return api_endpoints


class ContentAnalyzer:
    """
    Main content analyzer combining all analysis modules.

    Provides comprehensive analysis of crawled content including:
    - Technology stack detection
    - Contact information harvesting
    - API endpoint discovery
    - Metadata extraction
    """

    def __init__(self):
        self.tech_detector = TechnologyDetector()
        self.contact_harvester = ContactHarvester()
        self.api_discovery = APIDiscovery()

    def analyze(
        self,
        url: str,
        html: str,
        headers: dict[str, str] | None = None,
    ) -> AnalysisResult:
        """
        Perform comprehensive content analysis.

        Args:
            url: URL of the content
            html: HTML content
            headers: HTTP response headers

        Returns:
            AnalysisResult with all extracted data
        """
        result = AnalysisResult(url=url)

        # Technology detection
        result.tech_stack = self.tech_detector.detect(html, headers)

        # Contact harvesting
        result.contacts = self.contact_harvester.harvest(html)

        # API discovery
        result.api_endpoints = self.api_discovery.discover(html, url)

        # Basic metadata
        result.metadata = {
            "title": self._extract_title(html),
            "description": self._extract_meta_description(html),
            "tech_count": len(result.tech_stack),
            "contact_count": len(result.contacts),
            "api_count": len(result.api_endpoints),
        }

        logger.info(
            f"Analyzed {url}: {len(result.tech_stack)} techs, "
            f"{len(result.contacts)} contacts, {len(result.api_endpoints)} APIs"
        )

        return result

    @staticmethod
    def _extract_title(html: str) -> str | None:
        """Extract page title."""
        match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_meta_description(html: str) -> str | None:
        """Extract meta description."""
        match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else None
