"""
Reconnaissance module for active OSINT.

Provides DNS enumeration, WHOIS lookups, and subdomain discovery.
"""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiodns
import httpx
import whois

logger = logging.getLogger(__name__)


@dataclass
class DNSRecord:
    """DNS record result."""

    domain: str
    record_type: str
    value: str | list[str]
    ttl: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WHOISInfo:
    """WHOIS lookup result."""

    domain: str
    registrar: str | None = None
    creation_date: datetime | list[datetime] | None = None
    expiration_date: datetime | list[datetime] | None = None
    updated_date: datetime | list[datetime] | None = None
    name_servers: list[str] | None = None
    status: list[str] | None = None
    emails: list[str] | None = None
    dnssec: str | None = None
    org: str | None = None
    country: str | None = None
    raw: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class SubdomainResult:
    """Subdomain discovery result."""

    subdomain: str
    source: str  # e.g., "crt.sh", "bruteforce", "dns_zone"
    ip_addresses: list[str] = field(default_factory=list)
    alive: bool = True
    timestamp: datetime = field(default_factory=datetime.now)


class DNSResolver:
    """Async DNS resolver with support for multiple record types."""

    def __init__(self, nameservers: list[str] | None = None, timeout: int = 5):
        """
        Initialize DNS resolver.

        Args:
            nameservers: Custom DNS servers (defaults to system resolvers)
            timeout: Query timeout in seconds
        """
        self.nameservers = nameservers or ["8.8.8.8", "1.1.1.1"]  # Google, Cloudflare
        self.timeout = timeout
        self.resolver = aiodns.DNSResolver(
            timeout=timeout, nameservers=self.nameservers
        )

    async def query_a(self, domain: str) -> list[DNSRecord]:
        """Query A records (IPv4)."""
        try:
            results = await self.resolver.query(domain, "A")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="A",
                    value=result.host,
                    ttl=result.ttl,
                )
                for result in results
            ]
        except Exception as e:
            logger.debug(f"A record query failed for {domain}: {e}")
            return []

    async def query_aaaa(self, domain: str) -> list[DNSRecord]:
        """Query AAAA records (IPv6)."""
        try:
            results = await self.resolver.query(domain, "AAAA")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="AAAA",
                    value=result.host,
                    ttl=result.ttl,
                )
                for result in results
            ]
        except Exception as e:
            logger.debug(f"AAAA record query failed for {domain}: {e}")
            return []

    async def query_mx(self, domain: str) -> list[DNSRecord]:
        """Query MX records (mail servers)."""
        try:
            results = await self.resolver.query(domain, "MX")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="MX",
                    value=f"{result.priority} {result.host}",
                    ttl=result.ttl,
                )
                for result in results
            ]
        except Exception as e:
            logger.debug(f"MX record query failed for {domain}: {e}")
            return []

    async def query_txt(self, domain: str) -> list[DNSRecord]:
        """Query TXT records."""
        try:
            results = await self.resolver.query(domain, "TXT")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="TXT",
                    value=result.text.decode() if isinstance(result.text, bytes) else result.text,
                    ttl=result.ttl,
                )
                for result in results
            ]
        except Exception as e:
            logger.debug(f"TXT record query failed for {domain}: {e}")
            return []

    async def query_ns(self, domain: str) -> list[DNSRecord]:
        """Query NS records (nameservers)."""
        try:
            results = await self.resolver.query(domain, "NS")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="NS",
                    value=result.host,
                    ttl=result.ttl,
                )
                for result in results
            ]
        except Exception as e:
            logger.debug(f"NS record query failed for {domain}: {e}")
            return []

    async def query_cname(self, domain: str) -> list[DNSRecord]:
        """Query CNAME records."""
        try:
            result = await self.resolver.query(domain, "CNAME")
            return [
                DNSRecord(
                    domain=domain,
                    record_type="CNAME",
                    value=result.cname,
                    ttl=result.ttl,
                )
            ]
        except Exception as e:
            logger.debug(f"CNAME record query failed for {domain}: {e}")
            return []

    async def query_soa(self, domain: str) -> list[DNSRecord]:
        """Query SOA records (start of authority)."""
        try:
            result = await self.resolver.query(domain, "SOA")
            soa_data = {
                "mname": result.nsname,
                "rname": result.hostmaster,
                "serial": result.serial,
                "refresh": result.refresh,
                "retry": result.retry,
                "expire": result.expire,
                "minimum": result.minttl,
            }
            return [
                DNSRecord(
                    domain=domain,
                    record_type="SOA",
                    value=str(soa_data),
                    ttl=result.ttl,
                )
            ]
        except Exception as e:
            logger.debug(f"SOA record query failed for {domain}: {e}")
            return []

    async def query_all(self, domain: str) -> dict[str, list[DNSRecord]]:
        """Query all common DNS record types."""
        tasks = {
            "A": self.query_a(domain),
            "AAAA": self.query_aaaa(domain),
            "MX": self.query_mx(domain),
            "TXT": self.query_txt(domain),
            "NS": self.query_ns(domain),
            "CNAME": self.query_cname(domain),
            "SOA": self.query_soa(domain),
        }

        results = {}
        for record_type, task in tasks.items():
            try:
                records = await task
                if records:
                    results[record_type] = records
            except Exception as e:
                logger.debug(f"Failed to query {record_type} for {domain}: {e}")

        return results

    async def reverse_dns(self, ip: str) -> str | None:
        """Perform reverse DNS lookup (PTR record)."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, socket.gethostbyaddr, ip
            )
            return result[0]  # hostname
        except Exception as e:
            logger.debug(f"Reverse DNS failed for {ip}: {e}")
            return None


class WHOISLookup:
    """WHOIS information lookup."""

    @staticmethod
    async def lookup(domain: str) -> WHOISInfo | None:
        """
        Perform WHOIS lookup for a domain.

        Args:
            domain: Domain name to lookup

        Returns:
            WHOISInfo object or None if lookup fails
        """
        try:
            # Run blocking whois in executor
            result = await asyncio.get_event_loop().run_in_executor(
                None, whois.whois, domain
            )

            # Handle both dict and Domain object responses
            if isinstance(result, dict):
                data = result
            else:
                data = result.__dict__

            return WHOISInfo(
                domain=domain,
                registrar=data.get("registrar"),
                creation_date=data.get("creation_date"),
                expiration_date=data.get("expiration_date"),
                updated_date=data.get("updated_date"),
                name_servers=data.get("name_servers"),
                status=data.get("status"),
                emails=data.get("emails"),
                dnssec=data.get("dnssec"),
                org=data.get("org"),
                country=data.get("country"),
                raw=str(data),
            )
        except Exception as e:
            logger.error(f"WHOIS lookup failed for {domain}: {e}")
            return None


class SubdomainEnumerator:
    """
    Subdomain discovery using multiple techniques.

    Supports:
    - Certificate Transparency logs (crt.sh)
    - DNS bruteforce
    - Common subdomain wordlists
    """

    DEFAULT_SUBDOMAINS = [
        "www",
        "mail",
        "ftp",
        "localhost",
        "webmail",
        "smtp",
        "pop",
        "ns1",
        "webdisk",
        "ns2",
        "cpanel",
        "whm",
        "autodiscover",
        "autoconfig",
        "m",
        "imap",
        "test",
        "ns",
        "blog",
        "pop3",
        "dev",
        "www2",
        "admin",
        "forum",
        "news",
        "vpn",
        "ns3",
        "mail2",
        "new",
        "mysql",
        "old",
        "lists",
        "support",
        "mobile",
        "mx",
        "static",
        "docs",
        "beta",
        "shop",
        "sql",
        "secure",
        "demo",
        "cp",
        "calendar",
        "wiki",
        "web",
        "media",
        "email",
        "images",
        "img",
        "www1",
        "intranet",
        "portal",
        "video",
        "sip",
        "dns2",
        "api",
        "cdn",
        "stats",
        "dns1",
        "ns4",
        "www3",
        "dns",
        "search",
        "staging",
        "server",
        "mx1",
        "chat",
        "wap",
        "my",
        "svn",
        "mail1",
        "sites",
        "proxy",
        "ads",
        "host",
        "crm",
        "cms",
        "backup",
        "mx2",
        "lyncdiscover",
        "info",
        "apps",
        "download",
        "remote",
        "db",
        "forums",
        "store",
        "relay",
        "files",
        "newsletter",
        "app",
        "live",
        "owa",
        "en",
        "start",
        "sms",
        "office",
        "exchange",
        "ipv4",
    ]

    def __init__(
        self,
        dns_resolver: DNSResolver | None = None,
        timeout: int = 10,
        max_concurrent: int = 50,
    ):
        """
        Initialize subdomain enumerator.

        Args:
            dns_resolver: DNSResolver instance (creates new if None)
            timeout: HTTP timeout for certificate transparency
            max_concurrent: Max concurrent DNS queries
        """
        self.dns_resolver = dns_resolver or DNSResolver()
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self.client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def from_crt_sh(self, domain: str) -> list[SubdomainResult]:
        """
        Discover subdomains via Certificate Transparency logs (crt.sh).

        Args:
            domain: Base domain

        Returns:
            List of discovered subdomains
        """
        try:
            url = f"https://crt.sh/?q=%.{domain}&output=json"
            response = await self.client.get(url)
            response.raise_for_status()

            data = response.json()
            subdomains = set()

            for entry in data:
                name_value = entry.get("name_value", "")
                # Handle wildcard and newline-separated entries
                for subdomain in name_value.split("\n"):
                    subdomain = subdomain.strip().replace("*.", "")
                    if subdomain and subdomain.endswith(domain):
                        subdomains.add(subdomain)

            results = []
            for subdomain in subdomains:
                # Resolve IP addresses
                a_records = await self.dns_resolver.query_a(subdomain)
                ip_addresses = [record.value for record in a_records]

                results.append(
                    SubdomainResult(
                        subdomain=subdomain,
                        source="crt.sh",
                        ip_addresses=ip_addresses,
                        alive=bool(ip_addresses),
                    )
                )

            logger.info(f"Found {len(results)} subdomains via crt.sh for {domain}")
            return results

        except Exception as e:
            logger.error(f"Certificate Transparency lookup failed for {domain}: {e}")
            return []

    async def bruteforce(
        self, domain: str, wordlist: list[str] | None = None
    ) -> list[SubdomainResult]:
        """
        Bruteforce subdomains using a wordlist.

        Args:
            domain: Base domain
            wordlist: List of subdomain prefixes (uses DEFAULT_SUBDOMAINS if None)

        Returns:
            List of discovered subdomains
        """
        wordlist = wordlist or self.DEFAULT_SUBDOMAINS
        results = []

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def check_subdomain(prefix: str) -> SubdomainResult | None:
            async with semaphore:
                subdomain = f"{prefix}.{domain}"
                try:
                    a_records = await self.dns_resolver.query_a(subdomain)
                    if a_records:
                        ip_addresses = [record.value for record in a_records]
                        logger.info(f"Found subdomain: {subdomain} -> {ip_addresses}")
                        return SubdomainResult(
                            subdomain=subdomain,
                            source="bruteforce",
                            ip_addresses=ip_addresses,
                            alive=True,
                        )
                except Exception as e:
                    logger.debug(f"Bruteforce failed for {subdomain}: {e}")
                return None

        # Run bruteforce concurrently
        tasks = [check_subdomain(prefix) for prefix in wordlist]
        found = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None and exceptions
        results = [r for r in found if isinstance(r, SubdomainResult)]

        logger.info(
            f"Bruteforce found {len(results)}/{len(wordlist)} subdomains for {domain}"
        )
        return results

    async def enumerate(
        self,
        domain: str,
        use_crt: bool = True,
        use_bruteforce: bool = True,
        wordlist: list[str] | None = None,
    ) -> list[SubdomainResult]:
        """
        Enumerate subdomains using multiple techniques.

        Args:
            domain: Base domain
            use_crt: Use Certificate Transparency logs
            use_bruteforce: Use DNS bruteforce
            wordlist: Custom wordlist for bruteforce

        Returns:
            Combined list of discovered subdomains (deduplicated)
        """
        all_results = []

        # Run techniques concurrently
        tasks = []
        if use_crt:
            tasks.append(self.from_crt_sh(domain))
        if use_bruteforce:
            tasks.append(self.bruteforce(domain, wordlist))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate
        seen = set()
        for results in results_list:
            if isinstance(results, list):
                for result in results:
                    if result.subdomain not in seen:
                        seen.add(result.subdomain)
                        all_results.append(result)

        logger.info(f"Total unique subdomains found for {domain}: {len(all_results)}")
        return sorted(all_results, key=lambda x: x.subdomain)
