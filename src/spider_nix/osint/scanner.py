"""
Port scanning and service detection module.

Provides async TCP/UDP port scanning, banner grabbing, and service fingerprinting.
"""

import asyncio
import logging
import socket
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)


# Common service ports
COMMON_PORTS = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    111: "rpcbind",
    135: "msrpc",
    139: "netbios-ssn",
    143: "imap",
    443: "https",
    445: "microsoft-ds",
    993: "imaps",
    995: "pop3s",
    1723: "pptp",
    3306: "mysql",
    3389: "ms-wbt-server",
    5432: "postgresql",
    5900: "vnc",
    6379: "redis",
    8080: "http-proxy",
    8443: "https-alt",
    9200: "elasticsearch",
    27017: "mongodb",
}


@dataclass
class PortResult:
    """Port scan result."""

    host: str
    port: int
    protocol: Literal["tcp", "udp"]
    state: Literal["open", "closed", "filtered"]
    service: str | None = None
    banner: str | None = None
    version: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScanResult:
    """Complete scan result for a host."""

    host: str
    ports_scanned: int = 0
    ports_open: int = 0
    ports_closed: int = 0
    ports_filtered: int = 0
    scan_time_ms: float = 0
    results: list[PortResult] = field(default_factory=list)


class PortScanner:
    """
    Async port scanner with TCP/UDP support and service detection.

    Features:
    - Async TCP connect scanning
    - UDP probing
    - Banner grabbing
    - Service fingerprinting
    - Configurable concurrency and timeouts
    """

    def __init__(
        self,
        timeout: float = 2.0,
        max_concurrent: int = 100,
        banner_timeout: float = 3.0,
    ):
        """
        Initialize port scanner.

        Args:
            timeout: Connection timeout in seconds
            max_concurrent: Max concurrent port scans
            banner_timeout: Timeout for banner grabbing
        """
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.banner_timeout = banner_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def scan_tcp_port(self, host: str, port: int) -> PortResult:
        """
        Scan a single TCP port.

        Args:
            host: Target host
            port: Port number

        Returns:
            PortResult with scan details
        """
        async with self._semaphore:
            try:
                # Attempt TCP connection
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=self.timeout,
                )

                # Port is open, try to grab banner
                service = COMMON_PORTS.get(port)
                banner = None
                version = None

                try:
                    banner = await self._grab_banner(reader, writer, port)
                    if banner:
                        # Try to detect service version from banner
                        version = self._parse_version(banner)
                except Exception as e:
                    logger.debug(f"Banner grab failed for {host}:{port}: {e}")
                finally:
                    writer.close()
                    await writer.wait_closed()

                return PortResult(
                    host=host,
                    port=port,
                    protocol="tcp",
                    state="open",
                    service=service,
                    banner=banner,
                    version=version,
                )

            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                # Port closed or filtered
                return PortResult(
                    host=host,
                    port=port,
                    protocol="tcp",
                    state="closed",
                )

    async def scan_udp_port(self, host: str, port: int) -> PortResult:
        """
        Scan a single UDP port.

        Note: UDP scanning is unreliable - lack of response doesn't mean port is closed.

        Args:
            host: Target host
            port: Port number

        Returns:
            PortResult with scan details
        """
        async with self._semaphore:
            try:
                # Create UDP socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setblocking(False)
                sock.settimeout(self.timeout)

                # Send empty datagram
                await asyncio.get_event_loop().sock_sendto(
                    sock, b"", (host, port)
                )

                # Try to receive response
                try:
                    data, _ = await asyncio.wait_for(
                        asyncio.get_event_loop().sock_recvfrom(sock, 1024),
                        timeout=self.timeout,
                    )

                    service = COMMON_PORTS.get(port)
                    return PortResult(
                        host=host,
                        port=port,
                        protocol="udp",
                        state="open",
                        service=service,
                        banner=data.decode("utf-8", errors="ignore")[:100] if data else None,
                    )

                except asyncio.TimeoutError:
                    # No response - could be open or filtered
                    return PortResult(
                        host=host,
                        port=port,
                        protocol="udp",
                        state="filtered",
                    )

            except Exception as e:
                logger.debug(f"UDP scan failed for {host}:{port}: {e}")
                return PortResult(
                    host=host,
                    port=port,
                    protocol="udp",
                    state="filtered",
                )
            finally:
                sock.close()

    async def _grab_banner(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        port: int,
    ) -> str | None:
        """
        Grab service banner.

        Args:
            reader: Stream reader
            writer: Stream writer
            port: Port number

        Returns:
            Banner string or None
        """
        try:
            # Some services send banner immediately (SSH, FTP, SMTP)
            # Others need a probe (HTTP)

            # Wait for initial banner
            banner_data = await asyncio.wait_for(
                reader.read(1024),
                timeout=self.banner_timeout,
            )

            if banner_data:
                return banner_data.decode("utf-8", errors="ignore").strip()

            # No immediate banner, try HTTP probe
            if port in [80, 8080, 8443]:
                writer.write(b"GET / HTTP/1.0\r\n\r\n")
                await writer.drain()

                response = await asyncio.wait_for(
                    reader.read(1024),
                    timeout=self.banner_timeout,
                )

                if response:
                    return response.decode("utf-8", errors="ignore").strip()[:200]

        except (asyncio.TimeoutError, UnicodeDecodeError):
            pass

        return None

    @staticmethod
    def _parse_version(banner: str) -> str | None:
        """
        Parse version information from banner.

        Args:
            banner: Service banner

        Returns:
            Version string or None
        """
        # SSH
        if banner.startswith("SSH-"):
            return banner.split()[0]

        # HTTP Server
        if "Server:" in banner:
            for line in banner.split("\n"):
                if line.startswith("Server:"):
                    return line.split(":", 1)[1].strip()

        # FTP
        if "FTP" in banner.upper():
            parts = banner.split()
            if len(parts) >= 2:
                return parts[0]

        # Generic version pattern (e.g., "service/1.2.3")
        import re
        version_match = re.search(r"[\w\-]+[/\s](\d+\.[\d\.]+)", banner)
        if version_match:
            return version_match.group(0)

        return None

    async def scan_ports(
        self,
        host: str,
        ports: list[int] | None = None,
        protocol: Literal["tcp", "udp", "both"] = "tcp",
    ) -> ScanResult:
        """
        Scan multiple ports on a host.

        Args:
            host: Target host
            ports: List of ports to scan (None = common ports)
            protocol: Protocol to scan (tcp, udp, or both)

        Returns:
            ScanResult with all findings
        """
        start_time = asyncio.get_event_loop().time()

        # Default to common ports
        if ports is None:
            ports = list(COMMON_PORTS.keys())

        logger.info(f"Scanning {len(ports)} ports on {host} ({protocol})")

        tasks = []

        # Create scan tasks
        if protocol in ["tcp", "both"]:
            tasks.extend([self.scan_tcp_port(host, port) for port in ports])

        if protocol in ["udp", "both"]:
            tasks.extend([self.scan_udp_port(host, port) for port in ports])

        # Execute scans concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and aggregate
        valid_results = [r for r in results if isinstance(r, PortResult)]

        scan_result = ScanResult(
            host=host,
            ports_scanned=len(ports),
            results=valid_results,
        )

        # Count states
        for result in valid_results:
            if result.state == "open":
                scan_result.ports_open += 1
            elif result.state == "closed":
                scan_result.ports_closed += 1
            elif result.state == "filtered":
                scan_result.ports_filtered += 1

        scan_result.scan_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

        logger.info(
            f"Scan complete: {scan_result.ports_open} open, "
            f"{scan_result.ports_closed} closed, "
            f"{scan_result.ports_filtered} filtered "
            f"({scan_result.scan_time_ms:.0f}ms)"
        )

        return scan_result

    async def scan_range(
        self,
        host: str,
        start_port: int,
        end_port: int,
        protocol: Literal["tcp", "udp", "both"] = "tcp",
    ) -> ScanResult:
        """
        Scan a range of ports.

        Args:
            host: Target host
            start_port: Starting port
            end_port: Ending port (inclusive)
            protocol: Protocol to scan

        Returns:
            ScanResult with all findings
        """
        ports = list(range(start_port, end_port + 1))
        return await self.scan_ports(host, ports, protocol)

    async def scan_common_ports(
        self,
        host: str,
        protocol: Literal["tcp", "udp", "both"] = "tcp",
    ) -> ScanResult:
        """
        Scan common well-known ports.

        Args:
            host: Target host
            protocol: Protocol to scan

        Returns:
            ScanResult with all findings
        """
        return await self.scan_ports(host, None, protocol)


class ServiceDetector:
    """
    Advanced service detection and fingerprinting.

    Sends protocol-specific probes to identify services.
    """

    # Service probes (protocol-specific)
    PROBES = {
        "http": b"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n",
        "ssh": b"",  # SSH sends banner immediately
        "ftp": b"",  # FTP sends banner immediately
        "smtp": b"EHLO scanner\r\n",
        "pop3": b"USER test\r\n",
        "imap": b"A001 CAPABILITY\r\n",
    }

    @staticmethod
    async def detect_service(host: str, port: int, timeout: float = 3.0) -> dict:
        """
        Detect service running on a port.

        Args:
            host: Target host
            port: Port number
            timeout: Probe timeout

        Returns:
            Dict with service information
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )

            # Try common service probes
            service_info = {
                "port": port,
                "service": COMMON_PORTS.get(port, "unknown"),
                "banner": None,
                "fingerprint": None,
            }

            # Wait for banner or send probe
            try:
                # Try reading banner first
                banner = await asyncio.wait_for(
                    reader.read(512),
                    timeout=1.0,
                )

                if banner:
                    service_info["banner"] = banner.decode("utf-8", errors="ignore")
                else:
                    # No banner, try HTTP probe
                    if port in [80, 443, 8080, 8443]:
                        probe = b"GET / HTTP/1.0\r\n\r\n"
                        writer.write(probe)
                        await writer.drain()

                        response = await asyncio.wait_for(
                            reader.read(1024),
                            timeout=2.0,
                        )

                        if response:
                            service_info["banner"] = response.decode("utf-8", errors="ignore")
                            service_info["service"] = "http"

            except asyncio.TimeoutError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

            return service_info

        except Exception as e:
            logger.debug(f"Service detection failed for {host}:{port}: {e}")
            return {"port": port, "error": str(e)}
