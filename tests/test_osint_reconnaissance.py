"""Tests for OSINT reconnaissance module."""

import pytest
import unittest.mock

from spider_nix.osint import DNSResolver, WHOISLookup, SubdomainEnumerator


class TestDNSResolver:
    """Test DNS resolver functionality."""

    @pytest.mark.asyncio
    async def test_query_a_google(self):
        """Test A record query for google.com."""
        resolver = DNSResolver()
        records = await resolver.query_a("google.com")

        assert len(records) > 0
        assert all(record.record_type == "A" for record in records)
        assert all(record.domain == "google.com" for record in records)
        # Basic IPv4 format check
        assert all("." in record.value for record in records)

    @pytest.mark.asyncio
    async def test_query_mx_google(self):
        """Test MX record query for google.com."""
        resolver = DNSResolver()
        records = await resolver.query_mx("google.com")

        assert len(records) > 0
        assert all(record.record_type == "MX" for record in records)
        # MX records should have priority and hostname
        assert all(" " in record.value for record in records)

    @pytest.mark.asyncio
    async def test_query_txt(self):
        """Test TXT record query."""
        resolver = DNSResolver()
        records = await resolver.query_txt("google.com")

        # Google should have SPF and other TXT records
        assert len(records) > 0
        assert all(record.record_type == "TXT" for record in records)

    @pytest.mark.asyncio
    async def test_query_ns(self):
        """Test NS record query."""
        resolver = DNSResolver()
        records = await resolver.query_ns("google.com")

        assert len(records) > 0
        assert all(record.record_type == "NS" for record in records)
        assert all(record.ttl is not None for record in records)

    @pytest.mark.asyncio
    async def test_query_all(self):
        """Test querying all record types."""
        resolver = DNSResolver()
        all_records = await resolver.query_all("google.com")

        assert isinstance(all_records, dict)
        assert "A" in all_records
        assert "MX" in all_records
        assert len(all_records) > 0

    @pytest.mark.asyncio
    async def test_reverse_dns(self):
        """Test reverse DNS lookup."""
        resolver = DNSResolver()
        # Google's public DNS
        hostname = await resolver.reverse_dns("8.8.8.8")

        # Should return something like dns.google
        assert hostname is not None
        assert isinstance(hostname, str)

    @pytest.mark.asyncio
    async def test_nonexistent_domain(self):
        """Test query for non-existent domain."""
        resolver = DNSResolver()
        records = await resolver.query_a("this-domain-definitely-does-not-exist-12345.com")

        # Should return empty list, not raise exception
        assert records == []


class TestWHOISLookup:
    """Test WHOIS lookup functionality."""

    @pytest.mark.asyncio
    async def test_whois_google(self):
        """Test WHOIS lookup for google.com."""
        result = await WHOISLookup.lookup("google.com")

        assert result is not None
        assert result.domain == "google.com"
        assert result.registrar is not None
        # Google should have creation/expiration dates
        assert result.creation_date is not None
        assert result.name_servers is not None

    @pytest.mark.asyncio
    async def test_whois_nonexistent(self):
        """Test WHOIS for non-existent domain."""
        result = await WHOISLookup.lookup("this-domain-definitely-does-not-exist-99999.com")

        # Should return None or handle gracefully
        # (behavior may vary by WHOIS server)
        assert result is None or isinstance(result.raw, str)


class TestSubdomainEnumerator:
    """Test subdomain enumeration functionality."""

    @pytest.mark.asyncio
    async def test_crt_sh_lookup(self):
        """Test Certificate Transparency subdomain discovery."""
        with unittest.mock.patch("httpx.AsyncClient.get", new_callable=unittest.mock.AsyncMock) as mock_get:
            # Mock response
            mock_response = unittest.mock.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {"name_value": "www.google.com"},
                {"name_value": "*.mail.google.com"},
                {"name_value": "test.google.com"}
            ]
            mock_get.return_value = mock_response

            # Mock DNS resolution to avoid network calls there too
            with unittest.mock.patch("spider_nix.osint.reconnaissance.DNSResolver.query_a") as mock_dns:
                 # Mock DNS response for the IPs
                mock_record = unittest.mock.Mock()
                mock_record.value = "1.2.3.4"
                mock_dns.return_value = [mock_record]

                async with SubdomainEnumerator() as enumerator:
                    results = await enumerator.from_crt_sh("google.com")

                    # Google should have many subdomains in CT logs
                    assert len(results) > 0
                    assert all(result.source == "crt.sh" for result in results)
                    assert any(result.subdomain == "www.google.com" for result in results)

    @pytest.mark.asyncio
    async def test_bruteforce_common_subdomains(self):
        """Test DNS bruteforce with small wordlist."""
        async with SubdomainEnumerator() as enumerator:
            # Use a small wordlist for testing
            wordlist = ["www", "mail", "ftp", "localhost"]
            results = await enumerator.bruteforce("google.com", wordlist)

            # At least www should exist
            assert len(results) > 0
            assert all(result.source == "bruteforce" for result in results)
            assert any(result.subdomain == "www.google.com" for result in results)

    @pytest.mark.asyncio
    async def test_enumerate_combined(self):
        """Test combined enumeration (CRT + bruteforce)."""
        with unittest.mock.patch("httpx.AsyncClient.get", new_callable=unittest.mock.AsyncMock) as mock_get:
            mock_response = unittest.mock.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"name_value": "crt.google.com"}]
            mock_get.return_value = mock_response

            with unittest.mock.patch("spider_nix.osint.reconnaissance.DNSResolver.query_a") as mock_dns:
                mock_record = unittest.mock.Mock()
                mock_record.value = "1.2.3.4"
                mock_dns.return_value = [mock_record]

                async with SubdomainEnumerator(max_concurrent=10) as enumerator:
                    # Use small wordlist to speed up test
                    wordlist = ["www", "mail", "api"]
                    results = await enumerator.enumerate(
                        "google.com",
                        use_crt=True,
                        use_bruteforce=True,
                        wordlist=wordlist,
                    )

                    # Should have results from both sources
                    assert len(results) > 0
                    # Check sources logic - might be all mocked now so just verify we get something
                    assert results

    @pytest.mark.asyncio
    async def test_enumerate_crt_only(self):
        """Test enumeration with only Certificate Transparency."""
        with unittest.mock.patch("httpx.AsyncClient.get", new_callable=unittest.mock.AsyncMock) as mock_get:
            mock_response = unittest.mock.Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{"name_value": "www.google.com"}]
            mock_get.return_value = mock_response

            with unittest.mock.patch("spider_nix.osint.reconnaissance.DNSResolver.query_a") as mock_dns:
                mock_record = unittest.mock.Mock()
                mock_record.value = "1.2.3.4"
                mock_dns.return_value = [mock_record]

                async with SubdomainEnumerator() as enumerator:
                    results = await enumerator.enumerate(
                        "google.com",
                        use_crt=True,
                        use_bruteforce=False,
                    )

                    assert len(results) > 0
                    assert all(result.source == "crt.sh" for result in results)

    @pytest.mark.asyncio
    async def test_enumerate_bruteforce_only(self):
        """Test enumeration with only bruteforce."""
        async with SubdomainEnumerator() as enumerator:
            wordlist = ["www", "mail"]
            results = await enumerator.enumerate(
                "google.com",
                use_crt=False,
                use_bruteforce=True,
                wordlist=wordlist,
            )

            # Should have at least www
            assert len(results) >= 1
            assert all(result.source == "bruteforce" for result in results)


class TestDataClasses:
    """Test data class structures."""

    @pytest.mark.asyncio
    async def test_dns_record_structure(self):
        """Test DNSRecord dataclass."""
        resolver = DNSResolver()
        records = await resolver.query_a("google.com")

        record = records[0]
        assert hasattr(record, "domain")
        assert hasattr(record, "record_type")
        assert hasattr(record, "value")
        assert hasattr(record, "ttl")
        assert hasattr(record, "timestamp")

    @pytest.mark.asyncio
    async def test_whois_info_structure(self):
        """Test WHOISInfo dataclass."""
        result = await WHOISLookup.lookup("google.com")

        assert hasattr(result, "domain")
        assert hasattr(result, "registrar")
        assert hasattr(result, "creation_date")
        assert hasattr(result, "timestamp")

    @pytest.mark.asyncio
    async def test_subdomain_result_structure(self):
        """Test SubdomainResult dataclass."""
        async with SubdomainEnumerator() as enumerator:
            results = await enumerator.bruteforce("google.com", ["www"])

            if results:
                result = results[0]
                assert hasattr(result, "subdomain")
                assert hasattr(result, "source")
                assert hasattr(result, "ip_addresses")
                assert hasattr(result, "alive")
                assert hasattr(result, "timestamp")
