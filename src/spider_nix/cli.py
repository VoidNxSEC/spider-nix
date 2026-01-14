"""CLI interface for SpiderNix."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import CrawlerConfig, AGGRESSIVE_CONFIG
from .crawler import SpiderNix
from .browser import BrowserCrawler
from .proxy import ProxyRotator, fetch_public_proxies
from .storage import get_storage
from .osint import DNSResolver, WHOISLookup, SubdomainEnumerator, PortScanner
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


if __name__ == "__main__":
    app()
