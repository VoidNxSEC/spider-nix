"""
OSINT (Open Source Intelligence) module for SpiderNix.

This module provides active reconnaissance capabilities including:
- DNS enumeration and analysis
- WHOIS lookups
- Subdomain discovery
- Content analysis and data extraction
- Port scanning and service detection
- Vulnerability assessment
- External API integrations
- Correlation and graph analysis
- Advanced web discovery (GraphQL, forms, directories)
- Web intelligence (structured data, sitemaps, archives)
"""

from .reconnaissance import DNSResolver, WHOISLookup, SubdomainEnumerator
from .analyzer import ContentAnalyzer, TechnologyDetector, ContactHarvester, APIDiscovery, EnhancedTechStack
from .scanner import PortScanner, ServiceDetector
from .vulnerability import VulnerabilityScanner, SecurityHeadersChecker, CVEMatcher
from .integrations import ShodanClient, URLScanClient, VirusTotalClient, OSINTAggregator
from .correlator import CorrelationEngine, IntelligenceGraph, Entity, Relationship
from .web_discovery import (
    GraphQLEndpoint,
    GraphQLDiscovery,
    FormField,
    FormAnalysis,
    FormAnalyzer,
    DirectoryEntry,
    DirectoryBruteforcer,
    WellKnownResource,
    WellKnownScanner,
)
from .web_intelligence import (
    StructuredData,
    StructuredDataExtractor,
    SitemapURL,
    SitemapAnalysis,
    SitemapParser,
    RobotsRule,
    RobotsAnalysis,
    RobotsTxtAnalyzer,
    ArchiveSnapshot,
    ArchiveTimeline,
    WebArchiveClient,
)

__all__ = [
    # Reconnaissance
    "DNSResolver",
    "WHOISLookup",
    "SubdomainEnumerator",
    # Analysis
    "ContentAnalyzer",
    "TechnologyDetector",
    "ContactHarvester",
    "APIDiscovery",
    "EnhancedTechStack",
    # Scanning
    "PortScanner",
    "ServiceDetector",
    # Vulnerability
    "VulnerabilityScanner",
    "SecurityHeadersChecker",
    "CVEMatcher",
    # Integrations
    "ShodanClient",
    "URLScanClient",
    "VirusTotalClient",
    "OSINTAggregator",
    # Correlation
    "CorrelationEngine",
    "IntelligenceGraph",
    "Entity",
    "Relationship",
    # Web Discovery
    "GraphQLEndpoint",
    "GraphQLDiscovery",
    "FormField",
    "FormAnalysis",
    "FormAnalyzer",
    "DirectoryEntry",
    "DirectoryBruteforcer",
    "WellKnownResource",
    "WellKnownScanner",
    # Web Intelligence
    "StructuredData",
    "StructuredDataExtractor",
    "SitemapURL",
    "SitemapAnalysis",
    "SitemapParser",
    "RobotsRule",
    "RobotsAnalysis",
    "RobotsTxtAnalyzer",
    "ArchiveSnapshot",
    "ArchiveTimeline",
    "WebArchiveClient",
]
