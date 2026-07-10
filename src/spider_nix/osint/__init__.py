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

from .analyzer import (
    APIDiscovery,
    ContactHarvester,
    ContentAnalyzer,
    EnhancedTechStack,
    TechnologyDetector,
)
from .correlator import CorrelationEngine, Entity, IntelligenceGraph, Relationship
from .integrations import OSINTAggregator, ShodanClient, URLScanClient, VirusTotalClient
from .reconnaissance import DNSResolver, SubdomainEnumerator, WHOISLookup
from .scanner import PortScanner, ServiceDetector
from .vulnerability import CVEMatcher, SecurityHeadersChecker, VulnerabilityScanner
from .web_discovery import (
    DirectoryBruteforcer,
    DirectoryEntry,
    FormAnalysis,
    FormAnalyzer,
    FormField,
    GraphQLDiscovery,
    GraphQLEndpoint,
    WellKnownResource,
    WellKnownScanner,
)
from .web_intelligence import (
    ArchiveSnapshot,
    ArchiveTimeline,
    RobotsAnalysis,
    RobotsRule,
    RobotsTxtAnalyzer,
    SitemapAnalysis,
    SitemapParser,
    SitemapURL,
    StructuredData,
    StructuredDataExtractor,
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
