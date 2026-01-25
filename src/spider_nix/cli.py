"""CLI interface for SpiderNix."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import CrawlerConfig, AGGRESSIVE_CONFIG, get_preset, list_presets
from .crawler import SpiderNix
from .browser import BrowserCrawler
from .monitor import CrawlMonitor
from .proxy import ProxyRotator, fetch_public_proxies
from .report import generate_report
from .storage import get_storage
from .wizard import run_wizard
from .osint import DNSResolver, WHOISLookup, SubdomainEnumerator, PortScanner
from .osint import (
    GraphQLDiscovery,
    StructuredDataExtractor,
    TechnologyDetector,
    SitemapParser,
    RobotsTxtAnalyzer,
    FormAnalyzer,
    DirectoryBruteforcer,
    WellKnownScanner,
    WebArchiveClient,
)
from .intel.jobs import CareerPageFinder, JobAnalyzer, JobOpportunity

app = typer.Typer(
    name="spider-nix",
    help="🕷️ Enterprise web crawler for public data collection",
    add_completion=False,
)
console = Console()


@app.command()
def crawl(
    url: str = typer.Argument(..., help="URL to crawl"),
    pages: int = typer.Option(10, "--pages", "-p", help="Max pages to crawl"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, csv, sqlite"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Use browser for JS sites"),
    headless: bool = typer.Option(True, "--headless", help="Run browser headless"),
    follow: bool = typer.Option(False, "--follow", "-F", help="Follow links on pages"),
    proxy_file: Optional[Path] = typer.Option(None, "--proxy-file", help="File with proxy list"),
    concurrent: int = typer.Option(10, "--concurrent", "-c", help="Concurrent requests"),
    aggressive: bool = typer.Option(False, "--aggressive", "-a", help="Aggressive mode (fast, no delays)"),
    timeout: int = typer.Option(30, "--timeout", "-t", help="Request timeout in seconds"),
):
    """Crawl a URL and extract data."""
    
    console.print(f"\n[bold]🕷️ SpiderNix v{__version__}[/]\n")
    
    # Build config
    if aggressive:
        config = AGGRESSIVE_CONFIG.model_copy()
    else:
        config = CrawlerConfig()
    
    config.max_requests_per_crawl = pages
    config.max_concurrent_requests = concurrent
    config.request_timeout_ms = timeout * 1000
    config.use_browser = browser
    config.headless = headless
    
    # Load proxies if provided
    proxy_rotator = None
    if proxy_file:
        proxy_rotator = ProxyRotator.from_file(str(proxy_file))
        console.print(f"[cyan]Loaded {len(proxy_rotator.proxies)} proxies[/]")
    
    # Setup storage
    storage = None
    if output:
        storage = get_storage(output, format)
        console.print(f"[cyan]Output: {output} ({format})[/]")
    
    console.print(f"[cyan]Target: {url}[/]")
    console.print(f"[cyan]Mode: {'Browser' if browser else 'HTTP'} | Pages: {pages} | Concurrent: {concurrent}[/]\n")
    
    # Run crawler
    async def run():
        if browser:
            crawler = BrowserCrawler(config=config, proxy_rotator=proxy_rotator)
        else:
            crawler = SpiderNix(config=config, proxy_rotator=proxy_rotator)
        
        results = await crawler.crawl(
            url,
            max_pages=pages,
            follow_links=follow,
            storage=storage,
        )
        
        return results
    
    results = asyncio.run(run())
    
    # Summary
    console.print(f"\n[bold green]✓ Crawled {len(results)} pages[/]")
    if output:
        console.print(f"[green]Saved to: {output}[/]")


@app.command()
def proxy_fetch():
    """Fetch public proxies (unreliable, for testing only)."""
    
    console.print("[yellow]Fetching public proxies...[/]")
    
    async def run():
        return await fetch_public_proxies()
    
    proxies = asyncio.run(run())
    
    console.print(f"[green]Found {len(proxies)} proxies[/]\n")
    
    # Save to file
    with open("proxies.txt", "w") as f:
        for proxy in proxies:
            f.write(proxy + "\n")
    
    console.print("[green]Saved to: proxies.txt[/]")


@app.command()
def proxy_stats(
    proxy_file: Path = typer.Argument(..., help="Proxy file to analyze"),
    test: bool = typer.Option(False, "--test", "-t", help="Test proxies"),
):
    """Show proxy statistics."""
    
    rotator = ProxyRotator.from_file(str(proxy_file))
    
    console.print(f"[bold]Proxies: {len(rotator.proxies)}[/]\n")
    
    if test:
        console.print("[yellow]Testing proxies...[/]\n")
        
        import httpx
        
        async def test_proxy(proxy: str) -> tuple[str, bool, float]:
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    timeout=10,
                ) as client:
                    import time
                    start = time.monotonic()
                    resp = await client.get("https://httpbin.org/ip")
                    elapsed = (time.monotonic() - start) * 1000
                    return proxy, resp.status_code == 200, elapsed
            except Exception:
                return proxy, False, 0
        
        async def run():
            tasks = [test_proxy(p) for p in rotator.proxies[:20]]  # Test first 20
            return await asyncio.gather(*tasks)
        
        results = asyncio.run(run())
        
        table = Table(title="Proxy Test Results")
        table.add_column("Proxy", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Latency", style="yellow")
        
        for proxy, ok, latency in results:
            status = "✓ OK" if ok else "✗ Failed"
            lat = f"{latency:.0f}ms" if ok else "-"
            table.add_row(proxy[:50], status, lat)
        
        console.print(table)


@app.command()
def version():
    """Show version."""
    console.print(f"[bold]SpiderNix v{__version__}[/]")


# OSINT Reconnaissance commands
recon_app = typer.Typer(
    name="recon",
    help="🔍 OSINT reconnaissance commands (DNS, WHOIS, subdomains)",
)
app.add_typer(recon_app, name="recon")


@recon_app.command("dns")
def recon_dns(
    domain: str = typer.Argument(..., help="Domain to query"),
    record_type: Optional[str] = typer.Option(None, "--type", "-t", help="Specific record type (A, AAAA, MX, TXT, NS, CNAME, SOA)"),
    nameservers: Optional[str] = typer.Option(None, "--nameservers", "-n", help="Custom DNS servers (comma-separated)"),
    reverse: Optional[str] = typer.Option(None, "--reverse", "-r", help="Reverse DNS lookup for IP"),
):
    """Perform DNS enumeration."""

    console.print(f"\n[bold]🔍 DNS Reconnaissance: {domain or reverse}[/]\n")

    async def run():
        ns = nameservers.split(",") if nameservers else None
        resolver = DNSResolver(nameservers=ns)

        if reverse:
            # Reverse DNS
            hostname = await resolver.reverse_dns(reverse)
            if hostname:
                console.print(f"[green]{reverse} -> {hostname}[/]")
            else:
                console.print(f"[red]No PTR record found for {reverse}[/]")
            return

        if record_type:
            # Query specific type
            rtype = record_type.upper()
            query_map = {
                "A": resolver.query_a,
                "AAAA": resolver.query_aaaa,
                "MX": resolver.query_mx,
                "TXT": resolver.query_txt,
                "NS": resolver.query_ns,
                "CNAME": resolver.query_cname,
                "SOA": resolver.query_soa,
            }

            if rtype not in query_map:
                console.print(f"[red]Invalid record type: {rtype}[/]")
                return

            records = await query_map[rtype](domain)
            if records:
                table = Table(title=f"{rtype} Records")
                table.add_column("Value", style="cyan")
                table.add_column("TTL", style="yellow")

                for record in records:
                    table.add_row(str(record.value), str(record.ttl or "-"))

                console.print(table)
            else:
                console.print(f"[yellow]No {rtype} records found[/]")
        else:
            # Query all types
            all_records = await resolver.query_all(domain)

            if not all_records:
                console.print(f"[yellow]No DNS records found for {domain}[/]")
                return

            for rec_type, records in all_records.items():
                table = Table(title=f"{rec_type} Records")
                table.add_column("Value", style="cyan")
                table.add_column("TTL", style="yellow")

                for record in records:
                    value = str(record.value)
                    if len(value) > 80:
                        value = value[:77] + "..."
                    table.add_row(value, str(record.ttl or "-"))

                console.print(table)
                console.print()

    asyncio.run(run())
    console.print("[green]✓ DNS enumeration complete[/]")


@recon_app.command("whois")
def recon_whois(
    domain: str = typer.Argument(..., help="Domain to lookup"),
    show_raw: bool = typer.Option(False, "--raw", help="Show raw WHOIS data"),
):
    """Perform WHOIS lookup."""

    console.print(f"\n[bold]🔍 WHOIS Lookup: {domain}[/]\n")

    async def run():
        result = await WHOISLookup.lookup(domain)

        if not result:
            console.print(f"[red]WHOIS lookup failed for {domain}[/]")
            return

        # Display structured data
        table = Table(title="WHOIS Information")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        fields = [
            ("Domain", result.domain),
            ("Registrar", result.registrar),
            ("Organization", result.org),
            ("Country", result.country),
            ("Creation Date", result.creation_date),
            ("Expiration Date", result.expiration_date),
            ("Updated Date", result.updated_date),
            ("Status", result.status),
            ("Name Servers", result.name_servers),
            ("DNSSEC", result.dnssec),
            ("Emails", result.emails),
        ]

        for field, value in fields:
            if value:
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value[:3])
                    if len(result.__dict__.get(field.lower().replace(" ", "_")) or []) > 3:
                        value += "..."
                table.add_row(field, str(value))

        console.print(table)

        if show_raw and result.raw:
            console.print("\n[bold]Raw WHOIS Data:[/]")
            console.print(result.raw[:1000])

    asyncio.run(run())
    console.print("\n[green]✓ WHOIS lookup complete[/]")


@recon_app.command("subdomains")
def recon_subdomains(
    domain: str = typer.Argument(..., help="Domain to enumerate"),
    use_crt: bool = typer.Option(True, "--crt/--no-crt", help="Use Certificate Transparency"),
    use_bruteforce: bool = typer.Option(True, "--bruteforce/--no-bruteforce", help="Use DNS bruteforce"),
    wordlist: Optional[Path] = typer.Option(None, "--wordlist", "-w", help="Custom wordlist file"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
    max_concurrent: int = typer.Option(50, "--concurrent", "-c", help="Max concurrent DNS queries"),
):
    """Discover subdomains."""

    console.print(f"\n[bold]🔍 Subdomain Enumeration: {domain}[/]\n")

    async def run():
        # Load custom wordlist if provided
        custom_wordlist = None
        if wordlist:
            with open(wordlist) as f:
                custom_wordlist = [line.strip() for line in f if line.strip()]
            console.print(f"[cyan]Loaded {len(custom_wordlist)} entries from wordlist[/]")

        async with SubdomainEnumerator(max_concurrent=max_concurrent) as enumerator:
            console.print("[yellow]Enumerating subdomains...[/]")

            if use_crt:
                console.print("[cyan]→ Querying Certificate Transparency logs...[/]")
            if use_bruteforce:
                console.print(f"[cyan]→ Bruteforcing with {len(custom_wordlist or enumerator.DEFAULT_SUBDOMAINS)} subdomains...[/]")

            results = await enumerator.enumerate(
                domain,
                use_crt=use_crt,
                use_bruteforce=use_bruteforce,
                wordlist=custom_wordlist,
            )

            if not results:
                console.print(f"[yellow]No subdomains found for {domain}[/]")
                return

            # Display results
            table = Table(title=f"Discovered Subdomains ({len(results)})")
            table.add_column("Subdomain", style="cyan")
            table.add_column("IP Addresses", style="green")
            table.add_column("Source", style="yellow")

            for result in results:
                ips = ", ".join(result.ip_addresses[:2])
                if len(result.ip_addresses) > 2:
                    ips += f" +{len(result.ip_addresses) - 2}"
                table.add_row(result.subdomain, ips or "-", result.source)

            console.print(table)

            # Save to file if requested
            if output:
                import json
                data = [
                    {
                        "subdomain": r.subdomain,
                        "ip_addresses": r.ip_addresses,
                        "source": r.source,
                        "alive": r.alive,
                        "timestamp": r.timestamp.isoformat(),
                    }
                    for r in results
                ]

                with open(output, "w") as f:
                    json.dump(data, f, indent=2)

                console.print(f"\n[green]Saved to: {output}[/]")

    asyncio.run(run())
    console.print("\n[green]✓ Subdomain enumeration complete[/]")


@recon_app.command("portscan")
def recon_portscan(
    target: str = typer.Argument(..., help="Target host/IP"),
    ports: Optional[str] = typer.Option(None, "--ports", "-p", help="Ports to scan (e.g., 80,443 or 1-1000)"),
    common: bool = typer.Option(False, "--common", "-c", help="Scan common ports only"),
    protocol: str = typer.Option("tcp", "--protocol", help="Protocol: tcp, udp, or both"),
    timeout: float = typer.Option(2.0, "--timeout", "-t", help="Connection timeout in seconds"),
    concurrent: int = typer.Option(100, "--concurrent", help="Max concurrent scans"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Scan ports on target host."""

    console.print(f"\n[bold]🔍 Port Scan: {target}[/]\n")

    async def run():
        scanner = PortScanner(
            timeout=timeout,
            max_concurrent=concurrent,
        )

        # Parse ports
        port_list = None
        if ports:
            # Handle ranges (e.g., "1-1000") or comma-separated (e.g., "80,443,8080")
            if "-" in ports:
                start, end = map(int, ports.split("-", 1))
                console.print(f"[cyan]Scanning ports {start}-{end} ({protocol})...[/]")
                result = await scanner.scan_range(target, start, end, protocol)
            else:
                port_list = [int(p.strip()) for p in ports.split(",")]
                console.print(f"[cyan]Scanning {len(port_list)} ports ({protocol})...[/]")
                result = await scanner.scan_ports(target, port_list, protocol)
        elif common:
            console.print(f"[cyan]Scanning common ports ({protocol})...[/]")
            result = await scanner.scan_common_ports(target, protocol)
        else:
            # Default: scan top 100 ports
            from spider_nix.osint.scanner import COMMON_PORTS
            port_list = list(COMMON_PORTS.keys())
            console.print(f"[cyan]Scanning {len(port_list)} common ports ({protocol})...[/]")
            result = await scanner.scan_ports(target, port_list, protocol)

        if not result.results:
            console.print(f"[yellow]No results from scan[/]")
            return

        # Display open ports
        open_ports = [r for r in result.results if r.state == "open"]

        if open_ports:
            table = Table(title=f"Open Ports on {target} ({len(open_ports)})")
            table.add_column("Port", style="cyan")
            table.add_column("Protocol", style="yellow")
            table.add_column("Service", style="green")
            table.add_column("Version", style="white")
            table.add_column("Banner", style="dim")

            for port_result in open_ports:
                banner = (port_result.banner[:50] + "...") if port_result.banner and len(port_result.banner) > 50 else (port_result.banner or "-")
                table.add_row(
                    str(port_result.port),
                    port_result.protocol,
                    port_result.service or "unknown",
                    port_result.version or "-",
                    banner,
                )

            console.print(table)
        else:
            console.print("[yellow]No open ports found[/]")

        # Summary
        console.print(
            f"\n[bold]Summary:[/] {result.ports_open} open, "
            f"{result.ports_closed} closed, {result.ports_filtered} filtered "
            f"({result.scan_time_ms:.0f}ms)"
        )

        # Save to file if requested
        if output:
            import json
            data = {
                "host": result.host,
                "scan_time_ms": result.scan_time_ms,
                "ports_scanned": result.ports_scanned,
                "ports_open": result.ports_open,
                "open_ports": [
                    {
                        "port": r.port,
                        "protocol": r.protocol,
                        "service": r.service,
                        "version": r.version,
                        "banner": r.banner,
                        "timestamp": r.timestamp.isoformat(),
                    }
                    for r in open_ports
                ],
            }

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

    asyncio.run(run())
    console.print("\n[green]✓ Port scan complete[/]")


# Advanced Web Discovery & Intelligence commands
web_app = typer.Typer(
    name="web",
    help="🌐 Advanced web discovery and intelligence tools",
)
recon_app.add_typer(web_app, name="web")


@web_app.command("graphql")
def web_graphql(
    url: str = typer.Argument(..., help="URL to scan for GraphQL"),
    introspect: bool = typer.Option(True, "--introspect/--no-introspect", help="Attempt introspection query"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Discover GraphQL endpoints and introspect schemas."""

    console.print(f"\n[bold]🔍 GraphQL Discovery: {url}[/]\n")

    async def run():
        discovery = GraphQLDiscovery()
        endpoints = await discovery.discover(url)

        if not endpoints:
            console.print("[yellow]No GraphQL endpoints found[/]")
            return []

        # Display results
        table = Table(title=f"GraphQL Endpoints ({len(endpoints)})")
        table.add_column("URL", style="cyan")
        table.add_column("Introspection", style="yellow")
        table.add_column("Schema", style="green")
        table.add_column("Types", style="white")

        for endpoint in endpoints:
            table.add_row(
                endpoint.url,
                "✓" if endpoint.introspection_enabled else "✗",
                "✓" if endpoint.schema_available else "✗",
                str(len(endpoint.types)) if endpoint.types else "-",
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            data = [
                {
                    "url": e.url,
                    "introspection_enabled": e.introspection_enabled,
                    "schema_available": e.schema_available,
                    "types": e.types,
                    "queries": e.queries,
                    "mutations": e.mutations,
                    "directives": e.directives,
                    "confidence": e.confidence,
                }
                for e in endpoints
            ]

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return endpoints

    asyncio.run(run())
    console.print("\n[green]✓ GraphQL discovery complete[/]")


@web_app.command("structured")
def web_structured(
    url: str = typer.Argument(..., help="URL to scan"),
    format: str = typer.Option("all", "--format", "-f", help="Format: all, json-ld, opengraph, microdata, twitter"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Extract structured data (JSON-LD, Open Graph, microdata)."""

    console.print(f"\n[bold]📊 Structured Data Extraction: {url}[/]\n")

    async def run():
        import httpx

        # Fetch HTML
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            html = resp.text

        # Extract structured data
        extractor = StructuredDataExtractor()
        data = await extractor.extract(url, html)

        # Filter by format if specified
        if format != "all":
            data = [item for item in data if item.format == format]

        if not data:
            console.print(f"[yellow]No structured data found (format: {format})[/]")
            return []

        # Display results
        table = Table(title=f"Structured Data ({len(data)} items)")
        table.add_column("Schema Type", style="cyan")
        table.add_column("Format", style="yellow")
        table.add_column("Properties", style="white")

        for item in data:
            props = ", ".join(list(item.properties.keys())[:5])
            if len(item.properties) > 5:
                props += "..."

            table.add_row(
                item.schema_type,
                item.format,
                props or "-",
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            json_data = [
                {
                    "url": item.url,
                    "schema_type": item.schema_type,
                    "format": item.format,
                    "properties": item.properties,
                    "confidence": item.confidence,
                }
                for item in data
            ]

            with open(output, "w") as f:
                json.dump(json_data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return data

    asyncio.run(run())
    console.print("\n[green]✓ Structured data extraction complete[/]")


@web_app.command("tech")
def web_tech(
    url: str = typer.Argument(..., help="URL to analyze"),
    check_versions: bool = typer.Option(True, "--check-versions/--no-versions", help="Detect library versions"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Enhanced technology detection with versions."""

    console.print(f"\n[bold]🔧 Technology Detection: {url}[/]\n")

    async def run():
        import httpx

        # Fetch HTML and headers
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            html = resp.text
            headers = dict(resp.headers)

        # Detect technologies
        detector = TechnologyDetector()
        tech_stack = detector.detect_with_versions(html, headers)

        if not tech_stack:
            console.print("[yellow]No technologies detected[/]")
            return []

        # Display results
        table = Table(title=f"Technologies ({len(tech_stack)} detected)")
        table.add_column("Technology", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Version", style="green")
        table.add_column("CDN", style="white")
        table.add_column("Status", style="red")

        for tech in tech_stack:
            table.add_row(
                tech.name,
                tech.category,
                tech.version or "-",
                "✓" if tech.cdn_url else "-",
                "OUTDATED" if tech.outdated else "OK",
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            data = [
                {
                    "name": t.name,
                    "category": t.category,
                    "version": t.version,
                    "latest_version": t.latest_version,
                    "outdated": t.outdated,
                    "cdn_url": t.cdn_url,
                    "npm_package": t.npm_package,
                    "confidence": t.confidence,
                    "evidence": t.evidence,
                }
                for t in tech_stack
            ]

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return tech_stack

    asyncio.run(run())
    console.print("\n[green]✓ Technology detection complete[/]")


@web_app.command("sitemap")
def web_sitemap(
    url: str = typer.Argument(..., help="Base URL (will append /sitemap.xml)"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Parse nested sitemaps"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Parse sitemap.xml and extract URLs."""

    console.print(f"\n[bold]🗺️ Sitemap Parser: {url}[/]\n")

    async def run():
        # Construct sitemap URL
        from urllib.parse import urljoin
        sitemap_url = urljoin(url, "/sitemap.xml")

        parser = SitemapParser()
        analysis = await parser.parse(sitemap_url, recursive=recursive)

        if not analysis or analysis.url_count == 0:
            console.print("[yellow]No URLs found in sitemap[/]")
            return None

        # Display results
        console.print(f"[cyan]Total URLs: {analysis.url_count}[/]")
        console.print(f"[cyan]Nested Sitemaps: {len(analysis.nested_sitemaps)}[/]")

        if analysis.url_patterns:
            console.print(f"\n[bold]URL Patterns:[/]")
            for pattern, count in sorted(analysis.url_patterns.items(), key=lambda x: x[1], reverse=True)[:10]:
                console.print(f"  {pattern}: {count}")

        # Sample URLs
        console.print(f"\n[bold]Sample URLs (first 10):[/]")
        for url_entry in analysis.urls[:10]:
            console.print(f"  • {url_entry.loc}")

        # Save if requested
        if output:
            import json
            data = {
                "sitemap_url": analysis.sitemap_url,
                "url_count": analysis.url_count,
                "nested_sitemaps": analysis.nested_sitemaps,
                "url_patterns": analysis.url_patterns,
                "urls": [
                    {
                        "loc": u.loc,
                        "lastmod": u.lastmod.isoformat() if u.lastmod else None,
                        "changefreq": u.changefreq,
                        "priority": u.priority,
                    }
                    for u in analysis.urls
                ],
            }

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return analysis

    asyncio.run(run())
    console.print("\n[green]✓ Sitemap parsing complete[/]")


@web_app.command("robots")
def web_robots(
    domain: str = typer.Argument(..., help="Domain (will fetch /robots.txt)"),
    show_interesting: bool = typer.Option(True, "--show-interesting/--all", help="Show only interesting paths"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Parse robots.txt and find interesting paths."""

    console.print(f"\n[bold]🤖 Robots.txt Analyzer: {domain}[/]\n")

    async def run():
        analyzer = RobotsTxtAnalyzer()
        analysis = await analyzer.analyze(domain)

        if not analysis or not analysis.rules:
            console.print("[yellow]No robots.txt found or empty[/]")
            return None

        # Display sitemaps
        if analysis.sitemaps:
            console.print(f"[bold]Sitemaps ({len(analysis.sitemaps)}):[/]")
            for sitemap in analysis.sitemaps:
                console.print(f"  • {sitemap}")

        # Display crawl delay
        if analysis.crawl_delay:
            console.print(f"\n[yellow]Crawl Delay: {analysis.crawl_delay}s[/]")

        # Display rules
        console.print(f"\n[bold]Rules ({len(analysis.rules)}):[/]")
        for rule in analysis.rules[:5]:  # Show first 5 user-agents
            console.print(f"\n  User-agent: {rule.user_agent}")
            if rule.disallowed_paths:
                console.print(f"    Disallowed: {len(rule.disallowed_paths)} paths")
                for path in rule.disallowed_paths[:5]:
                    console.print(f"      - {path}")
            if rule.allowed_paths:
                console.print(f"    Allowed: {len(rule.allowed_paths)} paths")

        # Display interesting paths
        if analysis.interesting_paths:
            console.print(f"\n[bold red]Interesting Paths ({len(analysis.interesting_paths)}):[/]")
            for path in analysis.interesting_paths:
                console.print(f"  • {path}")

        # Save if requested
        if output:
            import json
            data = {
                "url": analysis.url,
                "crawl_delay": analysis.crawl_delay,
                "sitemaps": analysis.sitemaps,
                "interesting_paths": analysis.interesting_paths,
                "rules": [
                    {
                        "user_agent": r.user_agent,
                        "disallowed_paths": r.disallowed_paths,
                        "allowed_paths": r.allowed_paths,
                    }
                    for r in analysis.rules
                ],
            }

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return analysis

    asyncio.run(run())
    console.print("\n[green]✓ Robots.txt analysis complete[/]")


@web_app.command("forms")
def web_forms(
    url: str = typer.Argument(..., help="URL to scan for forms"),
    crawl_depth: int = typer.Option(1, "--crawl-depth", "-d", help="Crawl depth (1 = single page)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Discover and analyze HTML forms."""

    console.print(f"\n[bold]📝 Form Discovery: {url}[/]\n")

    async def run():
        import httpx

        # Fetch HTML
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True)
            html = resp.text

        # Analyze forms
        analyzer = FormAnalyzer()
        forms = await analyzer.analyze_page(url, html)

        if not forms:
            console.print("[yellow]No forms found[/]")
            return []

        # Display results
        table = Table(title=f"Forms ({len(forms)} found)")
        table.add_column("Action", style="cyan")
        table.add_column("Method", style="yellow")
        table.add_column("Purpose", style="green")
        table.add_column("Fields", style="white")
        table.add_column("CAPTCHA", style="red")

        for form in forms:
            table.add_row(
                form.action[:50] + "..." if len(form.action) > 50 else form.action,
                form.method.upper(),
                form.purpose or "unknown",
                str(form.field_count),
                "✓" if form.has_captcha else "✗",
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            data = [
                {
                    "url": f.url,
                    "action": f.action,
                    "method": f.method,
                    "purpose": f.purpose,
                    "field_count": f.field_count,
                    "has_captcha": f.has_captcha,
                    "has_file_upload": f.has_file_upload,
                    "complexity_score": f.complexity_score,
                    "fields": [
                        {
                            "name": field.name,
                            "type": field.field_type,
                            "required": field.required,
                            "placeholder": field.placeholder,
                        }
                        for field in f.fields
                    ],
                }
                for f in forms
            ]

            with open(output, "w") as f_out:
                json.dump(data, f_out, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return forms

    asyncio.run(run())
    console.print("\n[green]✓ Form discovery complete[/]")


@web_app.command("dirs")
def web_dirs(
    url: str = typer.Argument(..., help="Base URL to brute-force"),
    wordlist: Optional[str] = typer.Option(None, "--wordlist", "-w", help="Wordlist name (common_dirs, api_paths) or path"),
    extensions: Optional[str] = typer.Option(None, "--extensions", "-e", help="Extensions to try (comma-separated)"),
    threads: int = typer.Option(10, "--threads", "-t", help="Concurrent threads"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Directory and file brute-forcing."""

    console.print(f"\n[bold]📂 Directory Brute-force: {url}[/]\n")

    async def run():
        # Load wordlist
        wordlist_data = None
        if wordlist:
            if wordlist in ["common_dirs", "common_files", "api_paths"]:
                # Built-in wordlist
                from pathlib import Path as PathLib
                wordlist_path = PathLib(__file__).parent / "osint" / "wordlists" / f"{wordlist}.txt"
                if wordlist_path.exists():
                    wordlist_data = wordlist_path.read_text().strip().split("\n")
            else:
                # Custom wordlist file
                with open(wordlist) as f:
                    wordlist_data = [line.strip() for line in f if line.strip()]

        # Parse extensions
        ext_list = None
        if extensions:
            ext_list = [e.strip() for e in extensions.split(",")]

        # Run brute-force
        bruteforcer = DirectoryBruteforcer()
        console.print(f"[yellow]Starting brute-force (threads: {threads})...[/]")

        entries = await bruteforcer.bruteforce(
            url,
            wordlist=wordlist_data,
            extensions=ext_list,
            max_concurrent=threads,
        )

        if not entries:
            console.print("[yellow]No directories/files found[/]")
            return []

        # Display results
        table = Table(title=f"Discovered Paths ({len(entries)})")
        table.add_column("Path", style="cyan")
        table.add_column("Status", style="yellow")
        table.add_column("Size", style="white")
        table.add_column("Type", style="green")

        for entry in entries[:50]:  # Limit display
            size_str = f"{entry.size_bytes} bytes" if entry.size_bytes > 0 else "-"
            table.add_row(
                entry.path,
                str(entry.status_code),
                size_str,
                entry.content_type or "-",
            )

        console.print(table)

        if len(entries) > 50:
            console.print(f"\n[dim]... and {len(entries) - 50} more[/]")

        # Save if requested
        if output:
            import json
            data = [
                {
                    "path": e.path,
                    "status_code": e.status_code,
                    "size_bytes": e.size_bytes,
                    "content_type": e.content_type,
                    "redirect_url": e.redirect_url,
                    "discovered_via": e.discovered_via,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in entries
            ]

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return entries

    asyncio.run(run())
    console.print("\n[green]✓ Directory brute-force complete[/]")


@web_app.command("wellknown")
def web_wellknown(
    url: str = typer.Argument(..., help="Base URL to scan"),
    resources: str = typer.Option("all", "--resources", "-r", help="Resources to check (all or comma-separated)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Scan .well-known directory for resources."""

    console.print(f"\n[bold]🔐 Well-known Directory Scanner: {url}[/]\n")

    async def run():
        # Parse resources
        resource_list = None
        if resources != "all":
            resource_list = [r.strip() for r in resources.split(",")]

        # Scan
        scanner = WellKnownScanner()
        found_resources = await scanner.scan(url, resources=resource_list)

        if not found_resources:
            console.print("[yellow]No well-known resources found[/]")
            return []

        # Display results
        table = Table(title=f"Well-known Resources ({len(found_resources)} found)")
        table.add_column("Path", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Found", style="green")

        for resource in found_resources:
            table.add_row(
                f"/.well-known/{resource.path}",
                resource.resource_type,
                "✓" if resource.exists else "✗",
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            data = [
                {
                    "path": r.path,
                    "exists": r.exists,
                    "resource_type": r.resource_type,
                    "content": r.content,
                    "parsed_data": r.parsed_data,
                }
                for r in found_resources if r.exists
            ]

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return found_resources

    asyncio.run(run())
    console.print("\n[green]✓ Well-known scan complete[/]")


@web_app.command("archive")
def web_archive(
    url: str = typer.Argument(..., help="URL to query in Wayback Machine"),
    snapshots: int = typer.Option(10, "--snapshots", "-s", help="Max snapshots to retrieve"),
    from_date: Optional[str] = typer.Option(None, "--from-date", help="From date (YYYY-MM-DD)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
):
    """Query Wayback Machine for historical snapshots."""

    console.print(f"\n[bold]🕰️ Web Archive Query: {url}[/]\n")

    async def run():
        # Parse from_date
        from_datetime = None
        if from_date:
            from datetime import datetime
            from_datetime = datetime.strptime(from_date, "%Y-%m-%d")

        # Query archive
        client = WebArchiveClient()
        timeline = await client.get_timeline(url, limit=snapshots, from_date=from_datetime)

        if not timeline or timeline.snapshot_count == 0:
            console.print("[yellow]No snapshots found[/]")
            return None

        # Display summary
        console.print(f"[cyan]Total Snapshots: {timeline.snapshot_count}[/]")
        if timeline.first_seen:
            console.print(f"[cyan]First Seen: {timeline.first_seen.strftime('%Y-%m-%d')}[/]")
        if timeline.last_seen:
            console.print(f"[cyan]Last Seen: {timeline.last_seen.strftime('%Y-%m-%d')}[/]")

        # Display snapshots
        console.print(f"\n[bold]Snapshots (showing {len(timeline.snapshots)}):[/]")
        table = Table()
        table.add_column("Date", style="cyan")
        table.add_column("Status", style="yellow")
        table.add_column("Archive URL", style="dim")

        for snapshot in timeline.snapshots:
            table.add_row(
                snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                str(snapshot.status_code),
                snapshot.archive_url[:70] + "..." if len(snapshot.archive_url) > 70 else snapshot.archive_url,
            )

        console.print(table)

        # Save if requested
        if output:
            import json
            data = {
                "url": timeline.url,
                "first_seen": timeline.first_seen.isoformat() if timeline.first_seen else None,
                "last_seen": timeline.last_seen.isoformat() if timeline.last_seen else None,
                "snapshot_count": timeline.snapshot_count,
                "snapshots": [
                    {
                        "timestamp": s.timestamp.isoformat(),
                        "archive_url": s.archive_url,
                        "status_code": s.status_code,
                        "digest": s.digest,
                    }
                    for s in timeline.snapshots
                ],
            }

            with open(output, "w") as f:
                json.dump(data, f, indent=2)

            console.print(f"\n[green]Saved to: {output}[/]")

        return timeline

    asyncio.run(run())
    console.print("\n[green]✓ Archive query complete[/]")


@app.command("job-hunt")
def job_hunt(
    domain: str = typer.Argument(..., help="Company domain to scan (e.g. google.com)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
    pages: int = typer.Option(5, "--pages", "-p", help="Max pages to crawl per career site"),
):
    """Find and analyze job opportunities."""
    
    console.print(f"\n[bold]💼 Job Hunt: {domain}[/]\n")
    
    async def run():
        # 1. Find Career Pages
        console.print("[yellow]Finding career pages...[/]")
        finder = CareerPageFinder()
        career_urls = await finder.find(domain)
        
        if not career_urls:
            console.print(f"[red]No career pages found for {domain}[/]")
            return

        console.print(f"[green]Found {len(career_urls)} potential career sites:[/]")
        for url in career_urls:
            console.print(f"  - {url}")

        # 2. Crawl and Analyze
        console.print(f"\n[yellow]Scanning for opportunities (max {pages} pages each)...[/]")
        analyzer = JobAnalyzer()
        opportunities = []
        
        # Configure spider for this task
        config = CrawlerConfig()
        config.max_requests_per_crawl = pages
        config.max_concurrent_requests = 5
        spider = SpiderNix(config=config)
        
        for start_url in career_urls:
            console.print(f"[cyan]Scanning {start_url}...[/]")
            results = await spider.crawl(
                start_url, 
                max_pages=pages,
                follow_links=True,
                # Filter to keep within career sections usually
                link_filter=lambda x: any(k in x for k in ["career", "job", "position", "opening", "apply"])
            )
            
            for result in results:
                opp = analyzer.analyze_opportunity(result)
                if opp:
                    opportunities.append(opp)

        # 3. Report
        if not opportunities:
            console.print(f"\n[yellow]No specific job opportunities identified.[/]")
            return

        # Sort by score
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        table = Table(title=f"Job Opportunities at {domain} ({len(opportunities)})")
        table.add_column("Title", style="green")
        table.add_column("Seniority", style="cyan")
        table.add_column("Remote", style="magenta")
        table.add_column("Tech Stack", style="yellow")
        table.add_column("Score", style="white")
        table.add_column("URL", style="dim")

        for opp in opportunities:
            table.add_row(
                opp.title or "Unknown Title",
                opp.seniority or "-",
                opp.remote_policy or "-",
                ", ".join(opp.tech_stack[:3]),
                f"{opp.score:.1f}",
                opp.url
            )
            
        console.print(table)
        
        if output:
            import json
            data = [
                {
                    "company": o.company,
                    "title": o.title,
                    "url": o.url,
                    "seniority": o.seniority,
                    "remote": o.remote_policy,
                    "salary": o.salary_range,
                    "tech": o.tech_stack,
                    "score": o.score
                }
                for o in opportunities
            ]
            with open(output, "w") as f:
                json.dump(data, f, indent=2)
            console.print(f"\n[green]Saved to: {output}[/]")

    asyncio.run(run())
    console.print("\n[green]✓ Job hunt complete[/]")


@app.command()
def wizard():
    """🧙 Interactive configuration wizard."""
    console.print(f"\n[bold]🕷️ SpiderNix v{__version__}[/]\n")

    config = run_wizard()

    # Ask to save config
    from rich.prompt import Confirm, Prompt

    save = Confirm.ask("\n[cyan]Save configuration to file?[/]", default=False)
    if save:
        path = Prompt.ask("[cyan]Config file path[/]", default="spider_config.json")
        with open(path, "w") as f:
            f.write(config.model_dump_json(indent=2))
        console.print(f"[green]✓ Configuration saved to: {path}[/]")


@app.command()
def presets():
    """📋 List available configuration presets."""
    console.print(f"\n[bold]🕷️ SpiderNix Configuration Presets[/]\n")

    presets_info = list_presets()

    table = Table(title="Available Presets", show_header=True, header_style="bold cyan")
    table.add_column("Preset", style="cyan", width=15)
    table.add_column("Description", style="white")

    for name, description in presets_info.items():
        table.add_row(name, description)

    console.print(table)
    console.print("\n[dim]Usage: spider-nix advanced-crawl --preset <name>[/]")


@app.command()
def advanced_crawl(
    url: str = typer.Argument(..., help="URL to crawl"),
    pages: int = typer.Option(10, "--pages", "-p", help="Max pages to crawl"),
    preset: Optional[str] = typer.Option(None, "--preset", help="Config preset (run 'presets' to see options)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, csv, sqlite"),
    follow: bool = typer.Option(False, "--follow", "-F", help="Follow links on pages"),
    monitor: bool = typer.Option(True, "--monitor", help="Show real-time monitoring"),
    report: bool = typer.Option(False, "--report", help="Generate HTML report"),
    report_path: str = typer.Option("report.html", "--report-path", help="HTML report path"),
):
    """🚀 Advanced crawl with all features enabled."""
    console.print(f"\n[bold]🕷️ SpiderNix v{__version__} - Advanced Mode[/]\n")

    # Load config
    if preset:
        try:
            config = get_preset(preset)
            console.print(f"[cyan]Using preset: {preset}[/]")
        except ValueError as e:
            console.print(f"[red]Error: {e}[/]")
            raise typer.Exit(1)
    else:
        config = CrawlerConfig()

    config.max_requests_per_crawl = pages

    # Setup storage
    storage = None
    if output:
        storage = get_storage(output, format)
        console.print(f"[cyan]Output: {output} ({format})[/]")

    console.print(f"[cyan]Target: {url}[/]")
    console.print(f"[cyan]Features: Rate Limiting ✓ | Circuit Breaker ✓ | Deduplication ✓ | Monitoring ✓[/]\n")

    # Run crawler with advanced features
    async def run():
        # Initialize crawler with all features enabled
        crawler = SpiderNix(
            config=config,
            enable_adaptive_rate_limiting=True,
            enable_circuit_breaker=True,
            enable_deduplication=True,
        )

        # Setup monitor
        crawler_monitor = None
        if monitor:
            crawler_monitor = CrawlMonitor(max_pages=pages, show_live=True)
            crawler_monitor.start()

        try:
            results = await crawler.crawl(
                url,
                max_pages=pages,
                follow_links=follow,
                storage=storage,
            )

            # Update monitor with final results
            if crawler_monitor:
                for result in results:
                    if result and hasattr(result, 'status_code'):
                        crawler_monitor.update(
                            url=result.url,
                            status_code=result.status_code,
                            response_time_ms=result.metadata.get("elapsed_ms", 0),
                            success=200 <= result.status_code < 300,
                            bytes_downloaded=len(result.content) if result.content else 0,
                        )

                # Update rate limiter stats
                if crawler.rate_limiter:
                    stats = crawler.rate_limiter.get_stats()
                    crawler_monitor.update_rate_limiter(
                        stats.current_delay_ms,
                        stats.backpressure_detected,
                    )

                # Update circuit breaker
                if crawler.circuit_breaker:
                    crawler_monitor.update_circuit_breaker(
                        crawler.circuit_breaker.get_state().value
                    )

            return results, crawler_monitor
        finally:
            if crawler_monitor:
                crawler_monitor.stop()

    results, crawler_monitor = asyncio.run(run())

    # Print summary
    console.print(f"\n[bold green]✓ Crawled {len(results)} pages[/]")

    if crawler_monitor:
        crawler_monitor.print_summary()

    if output:
        console.print(f"[green]Saved to: {output}[/]")

    # Generate HTML report
    if report:
        console.print(f"\n[cyan]Generating HTML report...[/]")
        stats = crawler_monitor.stats if crawler_monitor else None
        report_file = generate_report(
            results=results,
            output_path=report_path,
            title=f"SpiderNix Crawl Report - {url}",
            stats=stats,
        )
        console.print(f"[green]✓ Report saved to: {report_file}[/]")


@app.command()
def generate_html_report(
    results_file: str = typer.Argument(..., help="Path to results file (JSON)"),
    output: str = typer.Option("report.html", "--output", "-o", help="Output HTML report path"),
    title: str = typer.Option("SpiderNix Crawl Report", "--title", "-t", help="Report title"),
):
    """📊 Generate HTML report from existing results."""
    import json
    from .storage import CrawlResult

    console.print(f"\n[bold]📊 Generating HTML Report[/]\n")

    # Load results
    with open(results_file) as f:
        data = json.load(f)

    # Convert to CrawlResult objects
    results = [CrawlResult(**item) for item in data]

    console.print(f"[cyan]Loaded {len(results)} results from {results_file}[/]")

    # Generate report
    report_file = generate_report(
        results=results,
        output_path=output,
        title=title,
    )

    console.print(f"[green]✓ Report saved to: {report_file}[/]")


if __name__ == "__main__":
    app()


@recon_app.command("multimodal")
def multimodal_extract(
    url: str = typer.Argument(..., help="Target URL"),
    output: Path = typer.Option("extraction.json", "--output", "-o", help="Output JSON file"),
    screenshot: Optional[Path] = typer.Option(None, "--screenshot", "-s", help="Save screenshot path"),
    headless: bool = typer.Option(True, "--headless", help="Run browser headless"),
    use_proxy: bool = typer.Option(True, "--proxy", help="Use network OPSEC proxy"),
    vision_model: str = typer.Option("llava-v1.5-7b-q4", "--model", "-m", help="Vision model to use"),
    iou_threshold: float = typer.Option(0.5, "--iou", help="IoU threshold for fusion (0-1)"),
):
    """
    🤖 Multimodal extraction - Vision + DOM fusion for CSS-independent scraping.
    
    Uses vision AI to detect elements visually, then fuses with DOM for
    high-confidence extractions resilient to CSS class changes.
    
    Example:
        spider-nix recon multimodal https://example.com
        spider-nix recon multimodal https://example.com --model llava-v1.5-7b-q4
        spider-nix recon multimodal https://example.com --iou 0.7 --proxy
    """
    import json
    from .extraction import MultimodalExtractor

    console.print(f"\n[bold]🤖 Multimodal Extraction[/]\n")
    console.print(f"Target: [cyan]{url}[/]")
    console.print(f"Vision Model: [yellow]{vision_model}[/]")
    console.print(f"IoU Threshold: [yellow]{iou_threshold}[/]")
    console.print(f"Network Proxy: [{'green' if use_proxy else 'red'}]{'enabled' if use_proxy else 'disabled'}[/]\n")

    async def run():
        extractor = MultimodalExtractor(
            iou_threshold=iou_threshold,
            vision_model=vision_model
        )

        try:
            # Extract from URL
            console.print("[cyan]→[/] Extracting elements...")
            result = await extractor.extract_from_url(
                url,
                headless=headless,
                use_network_proxy=use_proxy
            )

            # Save results
            with open(output, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)

            # Print summary
            console.print(f"\n[bold green]✓ Extraction Complete[/]\n")

            # Results table
            table = Table(title="Extraction Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="yellow")

            table.add_row("URL", url)
            table.add_row("Total Elements", str(result.total_elements))
            table.add_row("Fused (High Conf)", f"{result.fused_count} ({result.fusion_success_rate:.1f}%)")
            table.add_row("Vision Only", str(result.vision_only_count))
            table.add_row("DOM Only", str(result.dom_only_count))
            table.add_row("Resilient Elements", str(len(result.get_resilient_elements())))
            table.add_row("Average IoU", f"{result.average_iou:.3f}")
            table.add_row("Extraction Time", f"{result.extraction_time_ms:.0f}ms")
            table.add_row("Model Inference", f"{result.model_inference_time_ms:.0f}ms")
            table.add_row("Fusion Time", f"{result.fusion_time_ms:.0f}ms")

            console.print(table)

            # Elements breakdown
            console.print(f"\n[bold]Detected Elements:[/]")
            element_types = {}
            for elem in result.fused_elements:
                etype = elem.vision.element_type
                element_types[etype] = element_types.get(etype, 0) + 1

            for etype, count in sorted(element_types.items(), key=lambda x: x[1], reverse=True):
                console.print(f"  • {etype}: {count}")

            console.print(f"\n[green]✓ Results saved to: {output}[/]")
            if screenshot:
                console.print(f"[green]✓ Screenshot: {result.screenshot_path}[/]")

        finally:
            await extractor.close()

    asyncio.run(run())
