"""
Full validation test for all OSINT features.

Tests integration of all modules working together.
"""

import pytest

from spider_nix.osint import (
    DNSResolver,
    WHOISLookup,
    SubdomainEnumerator,
    ContentAnalyzer,
    PortScanner,
    VulnerabilityScanner,
    CorrelationEngine,
)


class TestFullIntegration:
    """Test full OSINT workflow integration."""

    @pytest.mark.asyncio
    async def test_reconnaissance_workflow(self):
        """Test complete reconnaissance workflow."""
        target = "example.com"

        # DNS Resolution
        resolver = DNSResolver()
        a_records = await resolver.query_a(target)
        assert len(a_records) > 0
        assert all(record.record_type == "A" for record in a_records)

        # WHOIS Lookup
        whois_result = await WHOISLookup.lookup(target)
        assert whois_result is not None
        assert whois_result.domain == target

    @pytest.mark.asyncio
    async def test_content_analysis_workflow(self):
        """Test content analysis workflow."""
        html = '''
        <html>
        <head><title>Test Site</title></head>
        <body>
        <script src="https://code.jquery.com/jquery.min.js"></script>
        <script src="https://www.google-analytics.com/analytics.js"></script>
        Contact: info@example.com
        </body>
        </html>
        '''

        headers = {
            "Server": "nginx/1.18.0",
            "X-Powered-By": "PHP/7.4",
        }

        # Content Analysis
        analyzer = ContentAnalyzer()
        result = analyzer.analyze("https://example.com", html, headers)

        assert len(result.tech_stack) > 0
        assert len(result.contacts) > 0

    @pytest.mark.asyncio
    async def test_port_scanning_workflow(self):
        """Test port scanning workflow."""
        scanner = PortScanner(timeout=1.0, max_concurrent=10)

        # Scan localhost
        result = await scanner.scan_ports("127.0.0.1", [22, 80, 443], "tcp")

        assert result.host == "127.0.0.1"
        assert result.ports_scanned == 3
        assert len(result.results) == 3

    def test_vulnerability_scanning(self):
        """Test vulnerability scanner."""
        scanner = VulnerabilityScanner()

        html = "<html><title>Index of /</title></html>"
        headers = {}  # Missing security headers

        result = scanner.scan(
            "https://example.com",
            headers=headers,
            html=html,
        )

        # Should find missing security headers
        assert len(result.issues) > 0
        assert any(issue.category == "header" for issue in result.issues)

    @pytest.mark.asyncio
    async def test_correlation_engine(self):
        """Test correlation engine."""
        engine = CorrelationEngine()

        # Simulate DNS results
        from spider_nix.osint.reconnaissance import DNSRecord

        dns_records = {
            "A": [
                DNSRecord(
                    domain="example.com",
                    record_type="A",
                    value="93.184.216.34",
                    ttl=3600,
                )
            ]
        }

        engine.process_dns_results("example.com", dns_records)

        # Check graph was built
        assert len(engine.graph.entities) >= 2  # domain + IP
        assert len(engine.graph.relationships) >= 1

        # Test graph export
        json_export = engine.graph.export_json()
        assert "entities" in json_export
        assert "relationships" in json_export

        dot_export = engine.graph.export_graphviz()
        assert "digraph OSINT" in dot_export

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test end-to-end OSINT workflow."""
        target = "example.com"
        engine = CorrelationEngine()

        # 1. DNS Enumeration
        resolver = DNSResolver()
        a_records = await resolver.query_a(target)
        dns_records = {"A": a_records}

        engine.process_dns_results(target, dns_records)

        # 2. Port Scanning (if we have IPs)
        if a_records:
            scanner = PortScanner(timeout=1.0)
            ip = a_records[0].value

            scan_result = await scanner.scan_ports(ip, [80, 443], "tcp")
            engine.process_port_scan(ip, scan_result)

        # 3. Content Analysis
        html = "<html><script src='jquery.min.js'></script></html>"
        headers = {"Server": "nginx"}

        analyzer = ContentAnalyzer()
        content_result = analyzer.analyze(f"https://{target}", html, headers)

        engine.process_tech_stack(f"https://{target}", content_result.tech_stack)

        # 4. Vulnerability Scan
        vuln_scanner = VulnerabilityScanner()
        vuln_result = vuln_scanner.scan(f"https://{target}", headers, html)

        engine.process_vulnerabilities(f"https://{target}", vuln_result.issues)

        # 5. Generate Report
        report = engine.generate_report()

        assert "statistics" in report
        assert "generated_at" in report
        assert report["statistics"]["total_entities"] > 0

    def test_all_modules_importable(self):
        """Test that all modules can be imported."""
        from spider_nix.osint import (
            DNSResolver,
            WHOISLookup,
            SubdomainEnumerator,
            ContentAnalyzer,
            TechnologyDetector,
            ContactHarvester,
            APIDiscovery,
            PortScanner,
            ServiceDetector,
            VulnerabilityScanner,
            SecurityHeadersChecker,
            CVEMatcher,
            ShodanClient,
            URLScanClient,
            VirusTotalClient,
            OSINTAggregator,
            CorrelationEngine,
            IntelligenceGraph,
            Entity,
            Relationship,
        )

        # All imports successful
        assert True


class TestModuleFeatures:
    """Test key features of each module."""

    def test_vulnerability_scanner_features(self):
        """Test vulnerability scanner capabilities."""
        scanner = VulnerabilityScanner()

        # Test missing security headers
        result = scanner.scan("https://test.com", headers={})
        header_issues = [i for i in result.issues if i.category == "header"]
        assert len(header_issues) > 0

        # Test debug mode detection
        html_debug = "<b>Fatal error</b>: Division by zero"
        result = scanner.scan("https://test.com", html=html_debug)
        debug_issues = [i for i in result.issues if "debug" in i.title.lower()]
        assert len(debug_issues) > 0

        # Test security score calculation
        assert 0 <= result.security_score <= 100

    def test_correlation_engine_features(self):
        """Test correlation engine capabilities."""
        from spider_nix.osint.correlator import Entity, Relationship

        engine = CorrelationEngine()

        # Add entities
        domain = Entity(id="domain:test.com", type="domain", value="test.com")
        ip = Entity(id="ip:1.2.3.4", type="ip", value="1.2.3.4")

        engine.graph.add_entity(domain)
        engine.graph.add_entity(ip)

        # Add relationship
        rel = Relationship(
            source_id="domain:test.com",
            target_id="ip:1.2.3.4",
            rel_type="resolves_to",
        )
        engine.graph.add_relationship(rel)

        # Test queries
        connected = engine.graph.get_connected_entities("domain:test.com")
        assert len(connected) == 1
        assert connected[0].id == "ip:1.2.3.4"

        # Test stats
        stats = engine.graph.get_stats()
        assert stats["total_entities"] == 2
        assert stats["total_relationships"] == 1
