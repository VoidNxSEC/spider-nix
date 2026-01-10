"""Tests for OSINT port scanner module."""

import pytest

from spider_nix.osint.scanner import PortScanner, ServiceDetector, COMMON_PORTS


class TestPortScanner:
    """Test port scanner functionality."""

    @pytest.mark.asyncio
    async def test_scan_tcp_port_open(self):
        """Test scanning an open TCP port (SSH on localhost)."""
        scanner = PortScanner(timeout=1.0)

        # Scan SSH port on localhost (usually open)
        result = await scanner.scan_tcp_port("127.0.0.1", 22)

        assert result.host == "127.0.0.1"
        assert result.port == 22
        assert result.protocol == "tcp"
        # SSH is usually open on dev machines
        assert result.state in ["open", "closed"]

        if result.state == "open":
            assert result.service == "ssh"
            # SSH should send banner
            assert result.banner is not None
            assert "SSH" in result.banner

    @pytest.mark.asyncio
    async def test_scan_tcp_port_closed(self):
        """Test scanning a closed TCP port."""
        scanner = PortScanner(timeout=1.0)

        # Port 9999 is unlikely to be open
        result = await scanner.scan_tcp_port("127.0.0.1", 9999)

        assert result.host == "127.0.0.1"
        assert result.port == 9999
        assert result.protocol == "tcp"
        assert result.state == "closed"

    @pytest.mark.asyncio
    async def test_scan_ports_list(self):
        """Test scanning multiple ports."""
        scanner = PortScanner(timeout=0.5, max_concurrent=10)

        # Scan common ports
        ports = [22, 80, 443, 9999]
        result = await scanner.scan_ports("127.0.0.1", ports, "tcp")

        assert result.host == "127.0.0.1"
        assert result.ports_scanned == len(ports)
        assert len(result.results) == len(ports)

        # Should have at least some closed ports
        assert result.ports_closed >= 1

    @pytest.mark.asyncio
    async def test_scan_range(self):
        """Test scanning a port range."""
        scanner = PortScanner(timeout=0.5, max_concurrent=20)

        # Scan small range
        result = await scanner.scan_range("127.0.0.1", 20, 25, "tcp")

        assert result.host == "127.0.0.1"
        assert result.ports_scanned == 6  # 20-25 inclusive
        assert len(result.results) == 6

    @pytest.mark.asyncio
    async def test_scan_common_ports(self):
        """Test scanning common ports."""
        scanner = PortScanner(timeout=0.5, max_concurrent=50)

        result = await scanner.scan_common_ports("127.0.0.1", "tcp")

        assert result.host == "127.0.0.1"
        assert result.ports_scanned == len(COMMON_PORTS)
        assert len(result.results) > 0

    @pytest.mark.asyncio
    async def test_parse_version(self):
        """Test version parsing from banners."""
        scanner = PortScanner()

        # SSH banner
        ssh_banner = "SSH-2.0-OpenSSH_8.2p1 Ubuntu-4ubuntu0.5"
        version = scanner._parse_version(ssh_banner)
        assert version is not None
        assert "SSH" in version

        # HTTP banner
        http_banner = "HTTP/1.1 200 OK\r\nServer: nginx/1.18.0\r\n"
        version = scanner._parse_version(http_banner)
        assert version is not None
        assert "nginx" in version.lower()

    @pytest.mark.asyncio
    async def test_concurrent_scanning(self):
        """Test that concurrent scanning works correctly."""
        scanner = PortScanner(timeout=0.5, max_concurrent=5)

        # Scan many ports concurrently
        ports = list(range(1, 51))  # First 50 ports
        result = await scanner.scan_ports("127.0.0.1", ports, "tcp")

        assert result.ports_scanned == 50
        assert len(result.results) == 50
        # Scan time should be reasonable (parallelized)
        assert result.scan_time_ms < 30000  # Less than 30 seconds


class TestServiceDetector:
    """Test service detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_ssh_service(self):
        """Test SSH service detection."""
        # Try to detect SSH on localhost
        result = await ServiceDetector.detect_service("127.0.0.1", 22, timeout=2.0)

        assert result["port"] == 22

        # If SSH is running
        if "banner" in result:
            banner = result.get("banner")
            if banner:
                assert "SSH" in banner or "OpenSSH" in banner

    @pytest.mark.asyncio
    async def test_detect_closed_port(self):
        """Test detection on closed port."""
        # Port 9999 is unlikely to be open
        result = await ServiceDetector.detect_service("127.0.0.1", 9999, timeout=1.0)

        assert result["port"] == 9999
        # Should have error or no banner
        assert "error" in result or result.get("banner") is None


class TestCommonPorts:
    """Test common ports dictionary."""

    def test_common_ports_exist(self):
        """Test that common ports are defined."""
        assert len(COMMON_PORTS) > 0
        assert 22 in COMMON_PORTS  # SSH
        assert 80 in COMMON_PORTS  # HTTP
        assert 443 in COMMON_PORTS  # HTTPS

    def test_common_ports_services(self):
        """Test that services are correctly mapped."""
        assert COMMON_PORTS[22] == "ssh"
        assert COMMON_PORTS[80] == "http"
        assert COMMON_PORTS[443] == "https"
        assert COMMON_PORTS[3306] == "mysql"
        assert COMMON_PORTS[5432] == "postgresql"
