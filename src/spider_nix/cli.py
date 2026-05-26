"""CLI interface for SpiderNix."""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .browser import BrowserCrawler
from .config import AGGRESSIVE_CONFIG, CrawlerConfig, get_preset, list_presets
from .crawler import SpiderNix
from .intel import (
    ApplicationTracker,
    CareerPageDiscoverer,
    HNHiringScraper,
    JobOpportunity,
    JobScorer,
    JobSeekerProfile,
    JobStorage,
    PreferredRemote,
    RemoteOKScraper,
    WeWorkRemotelyScraper,
    discover_and_scrape,
    match_jobs,
    scrape_all_boards,
)
from .intel.form_filler import (
    AutoFillProfile,
    FormAutoFiller,
    LiveFormFiller,
    autofill_url,
    live_fill_url,
)
from .intel.jobs import ApplicationStatus, JobSource, RemotePolicy, Seniority
from .intel.resume_parser import ResumeData, parse_resume
from .monitor import CrawlMonitor
from .osint import (
    DirectoryBruteforcer,
    DNSResolver,
    FormAnalyzer,
    GraphQLDiscovery,
    PortScanner,
    RobotsTxtAnalyzer,
    SitemapParser,
    StructuredDataExtractor,
    SubdomainEnumerator,
    TechnologyDetector,
    WebArchiveClient,
    WellKnownScanner,
    WHOISLookup,
)
from .proxy import ProxyRotator, fetch_public_proxies
from .report import generate_report
from .server import start_server
from .storage import get_storage
from .wizard import run_wizard

app = typer.Typer(
    name="spider",
    help="🕷️ Enterprise web crawler for public data collection",
    add_completion=False,
)
console = Console()

TYPECHECK_TARGETS = [
    "src/spider_nix/config.py",
    "src/spider_nix/stealth.py",
    "src/spider_nix/browser.py",
    "src/spider_nix/ml/models.py",
    "src/spider_nix/ml/failure_classifier.py",
    "src/spider_nix/extraction/models.py",
    "src/spider_nix/extraction/fusion_engine.py",
    "src/spider_nix/osint/web_discovery.py",
    "src/spider_nix/osint/web_intelligence.py",
]


def _find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "flake.nix").exists():
            return candidate
    console.print("[red]Could not locate repository root from the current directory.[/]")
    raise typer.Exit(1)


def _run_command(command: list[str], cwd: Optional[Path] = None) -> None:
    """Run a repository workflow command and propagate its exit status."""
    repo_root = _find_repo_root()
    resolved_cwd = (repo_root / cwd) if cwd else repo_root
    result = subprocess.run(command, cwd=str(resolved_cwd), check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


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
    aggressive: bool = typer.Option(
        False, "--aggressive", "-a", help="Aggressive mode (fast, no delays)"
    ),
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
    console.print(
        f"[cyan]Mode: {'Browser' if browser else 'HTTP'} | Pages: {pages} | Concurrent: {concurrent}[/]\n"
    )

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


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """🌐 Start the web GUI."""
    console.print(f"\n[bold]🌐 Spider-Nix Web GUI[/]\n")
    console.print(f"   URL: http://{host}:{port}")
    console.print(f"   Press Ctrl+C to stop\n")
    start_server(host, port, open_browser=not no_browser)


@app.command()
def test():
    """Run the test suite."""
    _run_command([sys.executable, "-m", "pytest", "tests/", "-v"])


@app.command("test-cov")
def test_cov():
    """Run tests with coverage reporting."""
    _run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--cov=src/spider_nix",
            "--cov-report=html",
            "--cov-report=term",
        ]
    )


@app.command()
def lint():
    """Run Ruff lint checks."""
    _run_command([sys.executable, "-m", "ruff", "check", "src/spider_nix"])


@app.command()
def check():
    """Run the standard lint check."""
    lint()


@app.command()
def fmt():
    """Format project code with Ruff."""
    _run_command([sys.executable, "-m", "ruff", "format", "src/spider_nix", "tests"])


@app.command()
def typecheck():
    """Run mypy on the CI-stabilized module set."""
    _run_command(
        [
            sys.executable,
            "-m",
            "mypy",
            *TYPECHECK_TARGETS,
            "--ignore-missing-imports",
            "--follow-imports=skip",
        ]
    )


@app.command()
def security():
    """Run security scans."""
    _run_command([sys.executable, "-m", "bandit", "-r", "src/spider_nix", "-ll"])


@app.command("hooks-install")
def hooks_install():
    """Install pre-commit hooks."""
    _run_command(["pre-commit", "install"])


@app.command("hooks-run")
def hooks_run():
    """Run pre-commit on all files."""
    _run_command(["pre-commit", "run", "--all-files"])


@app.command()
def clean():
    """Clean local build and test artifacts."""
    repo_root = _find_repo_root()
    directories = [
        "build",
        "dist",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
    ]
    file_patterns = ["*.egg-info", "*.pyc"]

    for relative_path in directories:
        shutil.rmtree(repo_root / relative_path, ignore_errors=True)

    for pattern in file_patterns:
        for path in repo_root.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    for path in repo_root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    console.print("[green]✓ Cleaned build and test artifacts[/]")


@app.command("ci-local")
def ci_local():
    """Run the local CI command set."""
    lint()
    typecheck()
    security()
    test()


@app.command("proxy-start")
def proxy_start():
    """Start the Go proxy server."""
    _run_command(
        ["go", "run", "./cmd/spider-network-proxy", "-config", "configs/test.toml"],
        cwd=Path("network"),
    )


@app.command("proxy-build")
def proxy_build():
    """Build the Go proxy binary."""
    _run_command(
        ["go", "build", "-o", "../dist/spider-network-proxy", "./cmd/spider-network-proxy"],
        cwd=Path("network"),
    )


@app.command()
def benchmark(
    url: str = typer.Argument(..., help="URL to benchmark"),
):
    """Benchmark crawl performance."""
    console.print(f"[cyan]Running performance benchmark on {url}[/]")
    _run_command(["hyperfine", "--warmup", "3", f"{sys.executable} -m spider_nix.cli crawl {url}"])


# OSINT Reconnaissance commands
recon_app = typer.Typer(
    name="recon",
    help="🔍 OSINT reconnaissance commands (DNS, WHOIS, subdomains)",
)
app.add_typer(recon_app, name="recon")


# ─── Job Intelligence commands ─────────────────────────────────────────────
job_app = typer.Typer(
    name="job",
    help="💼 Professional job hunt — search, track, autofill, manage profile",
)
app.add_typer(job_app, name="job")


# ─── Status Dashboard ─────────────────────────────────────────────────────


@app.command("status")
def status(
    db: Path = typer.Option("jobs.db", "--db", "-d", help="SQLite database path"),
):
    """📊 Quick dashboard — jobs, pipeline, profile status."""
    console.print("\n[bold]📊 Spider-Nix Status[/]\n")

    async def run():
        storage = JobStorage(db)
        try:
            # Job count
            total = await storage.count_jobs()
            console.print(f"[bold]💼 Jobs in database:[/] {total}")

            # Pipeline
            tracker = ApplicationTracker(storage)
            report = await tracker.pipeline_summary()
            console.print(report)

            # Profile
            profile = await storage.load_profile()
            if profile:
                console.print("\n[bold]👤 Profile:[/] configured")
                if profile.skills:
                    console.print(f"   Skills: {', '.join(profile.skills[:10])}")
                if profile.desired_titles:
                    console.print(f"   Titles: {', '.join(profile.desired_titles[:5])}")
                console.print(f"   Remote: {profile.preferred_remote.value}")
                if profile.min_salary:
                    console.print(
                        f"   Min Salary: {profile.preferred_currency} {profile.min_salary:,.0f}"
                    )
            else:
                console.print(
                    "\n[yellow]👤 Profile: not configured. Run 'spider job profile' to set up.[/]"
                )

            # Quick tips
            console.print("\n[dim]Quick actions:[/]")
            console.print("  [dim]spider job hunt --skills '...' --save-db jobs.db[/]")
            console.print("  [dim]spider job track --summary[/]")
            console.print("  [dim]spider job fill <url> --profile me.json --live[/]")

        finally:
            await storage.close()

    asyncio.run(run())
    console.print("\n[green]✓ Done[/]")


# ─── Job subcommands ──────────────────────────────────────────────────────


@job_app.command("hunt")
def job_hunt_alias(
    domain: str = typer.Argument(
        None, help="Company domain (optional). If omitted, searches all job boards."
    ),
    skills: Optional[str] = typer.Option(
        None, "--skills", "-s", help="Your skills (e.g. 'python,rust,nix')"
    ),
    titles: Optional[str] = typer.Option(None, "--titles", "-t", help="Desired job titles"),
    remote: str = typer.Option(
        "any", "--remote", "-r", help="remote_only, remote_preferred, hybrid_ok, any"
    ),
    min_salary: Optional[float] = typer.Option(None, "--min-salary", help="Minimum salary"),
    currency: str = typer.Option("USD", "--currency", "-c", help="USD, EUR, BRL, GBP"),
    seniority: Optional[str] = typer.Option(
        None, "--seniority", help="junior, mid, senior, staff, principal"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Export to JSON"),
    save_db: Optional[Path] = typer.Option(None, "--save-db", help="Save to SQLite database"),
    max_jobs: int = typer.Option(100, "--max", "-m", help="Maximum jobs to return"),
    include_ats: bool = typer.Option(True, "--ats/--no-ats"),
    include_boards: bool = typer.Option(True, "--boards/--no-boards"),
):
    """🔍 Search jobs across ATS platforms and job boards."""
    # Delegate to the main job_hunt implementation
    return job_hunt(
        domain=domain,
        skills=skills,
        titles=titles,
        remote=remote,
        min_salary=min_salary,
        currency=currency,
        seniority=seniority,
        output=output,
        save_db=save_db,
        max_jobs=max_jobs,
        include_ats=include_ats,
        include_boards=include_boards,
    )


@job_app.command("track")
def job_track_alias(
    db: Path = typer.Option("jobs.db", "--db", "-d"),
    job_id: Optional[str] = typer.Option(None, "--id", "-i", help="Job ID to update"),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="New status: saved, applied, phone_screen, technical, onsite, offer, accepted, rejected, withdrawn",
    ),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Add notes"),
    list_status: Optional[str] = typer.Option(None, "--list", "-l", help="List by status"),
    summary: bool = typer.Option(False, "--summary", help="Show pipeline summary"),
    export_json: Optional[Path] = typer.Option(None, "--export", "-e", help="Export to JSON"),
):
    """📋 Track applications through hiring pipeline."""
    return job_track(
        db=db,
        job_id=job_id,
        status=status,
        notes=notes,
        list_status=list_status,
        summary=summary,
        export_json=export_json,
    )


@job_app.command("profile")
def job_profile_alias(
    db: Path = typer.Option("jobs.db", "--db", "-d"),
    skills: Optional[str] = typer.Option(None, "--skills", "-s", help="Skills (comma-separated)"),
    titles: Optional[str] = typer.Option(None, "--titles", "-t", help="Desired job titles"),
    remote: Optional[str] = typer.Option(None, "--remote", "-r", help="Remote preference"),
    min_salary: Optional[float] = typer.Option(None, "--min-salary"),
    currency: str = typer.Option("USD", "--currency", "-c"),
    show: bool = typer.Option(False, "--show", help="Show current profile"),
    from_resume: Optional[Path] = typer.Option(
        None, "--from-resume", help="Parse resume PDF/DOCX/TXT"
    ),
):
    """👤 Manage your job seeker profile."""
    return job_profile(
        db=db,
        skills=skills,
        titles=titles,
        remote=remote,
        min_salary=min_salary,
        currency=currency,
        show=show,
        from_resume=from_resume,
    )


@job_app.command("fill")
def autofill_alias(
    url: str = typer.Argument(..., help="URL of the application form"),
    profile_json: Optional[Path] = typer.Option(None, "--profile", "-p", help="JSON profile file"),
    first_name: Optional[str] = typer.Option(None, "--first-name"),
    last_name: Optional[str] = typer.Option(None, "--last-name"),
    full_name: Optional[str] = typer.Option(None, "--full-name"),
    email: Optional[str] = typer.Option(None, "--email"),
    phone: Optional[str] = typer.Option(None, "--phone"),
    linkedin: Optional[str] = typer.Option(None, "--linkedin"),
    github: Optional[str] = typer.Option(None, "--github"),
    portfolio: Optional[str] = typer.Option(None, "--portfolio"),
    resume: Optional[Path] = typer.Option(None, "--resume"),
    cover_letter: Optional[str] = typer.Option(None, "--cover-letter"),
    salary: Optional[str] = typer.Option(None, "--salary"),
    location: Optional[str] = typer.Option(None, "--location"),
    work_auth: Optional[str] = typer.Option(None, "--work-auth"),
    years_exp: Optional[str] = typer.Option(None, "--years-exp"),
    education: Optional[str] = typer.Option(None, "--education"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    generate_script: Optional[Path] = typer.Option(None, "--generate-script", "-g"),
    generate_curl: Optional[Path] = typer.Option(None, "--generate-curl"),
    use_chrome: bool = typer.Option(False, "--use-chrome"),
    chrome_profile: Optional[str] = typer.Option(None, "--chrome-profile"),
    live: bool = typer.Option(False, "--live", help="Interactive browser mode"),
):
    """🤖 Auto-fill application forms — analyze + fill with confidence scoring."""
    return autofill(
        url=url,
        profile_json=profile_json,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        email=email,
        phone=phone,
        linkedin=linkedin,
        github=github,
        portfolio=portfolio,
        resume=resume,
        cover_letter=cover_letter,
        salary=salary,
        location=location,
        work_auth=work_auth,
        years_exp=years_exp,
        education=education,
        output=output,
        generate_script=generate_script,
        generate_curl=generate_curl,
        use_chrome=use_chrome,
        chrome_profile=chrome_profile,
        live=live,
    )


@recon_app.command("dns")
def recon_dns(
    domain: str = typer.Argument(..., help="Domain to query"),
    record_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Specific record type (A, AAAA, MX, TXT, NS, CNAME, SOA)"
    ),
    nameservers: Optional[str] = typer.Option(
        None, "--nameservers", "-n", help="Custom DNS servers (comma-separated)"
    ),
    reverse: Optional[str] = typer.Option(
        None, "--reverse", "-r", help="Reverse DNS lookup for IP"
    ),
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
    use_bruteforce: bool = typer.Option(
        True, "--bruteforce/--no-bruteforce", help="Use DNS bruteforce"
    ),
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
                console.print(
                    f"[cyan]→ Bruteforcing with {len(custom_wordlist or enumerator.DEFAULT_SUBDOMAINS)} subdomains...[/]"
                )

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
    ports: Optional[str] = typer.Option(
        None, "--ports", "-p", help="Ports to scan (e.g., 80,443 or 1-1000)"
    ),
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
            console.print("[yellow]No results from scan[/]")
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
                banner = (
                    (port_result.banner[:50] + "...")
                    if port_result.banner and len(port_result.banner) > 50
                    else (port_result.banner or "-")
                )
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
    introspect: bool = typer.Option(
        True, "--introspect/--no-introspect", help="Attempt introspection query"
    ),
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
    format: str = typer.Option(
        "all", "--format", "-f", help="Format: all, json-ld, opengraph, microdata, twitter"
    ),
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
    check_versions: bool = typer.Option(
        True, "--check-versions/--no-versions", help="Detect library versions"
    ),
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
    recursive: bool = typer.Option(
        True, "--recursive/--no-recursive", help="Parse nested sitemaps"
    ),
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
            console.print("\n[bold]URL Patterns:[/]")
            for pattern, count in sorted(
                analysis.url_patterns.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                console.print(f"  {pattern}: {count}")

        # Sample URLs
        console.print("\n[bold]Sample URLs (first 10):[/]")
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
    show_interesting: bool = typer.Option(
        True, "--show-interesting/--all", help="Show only interesting paths"
    ),
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


@app.command("autofill")
def autofill(
    url: str = typer.Argument(..., help="URL of the page with the form to fill"),
    profile_json: Optional[Path] = typer.Option(
        None, "--profile", "-p", help="JSON profile file with your data"
    ),
    first_name: Optional[str] = typer.Option(None, "--first-name", help="First name"),
    last_name: Optional[str] = typer.Option(None, "--last-name", help="Last name"),
    full_name: Optional[str] = typer.Option(None, "--full-name", help="Full name"),
    email: Optional[str] = typer.Option(None, "--email", help="Email address"),
    phone: Optional[str] = typer.Option(None, "--phone", help="Phone number"),
    linkedin: Optional[str] = typer.Option(None, "--linkedin", help="LinkedIn URL"),
    github: Optional[str] = typer.Option(None, "--github", help="GitHub URL"),
    portfolio: Optional[str] = typer.Option(None, "--portfolio", help="Portfolio URL"),
    resume: Optional[Path] = typer.Option(None, "--resume", help="Path to resume/CV file"),
    cover_letter: Optional[str] = typer.Option(
        None, "--cover-letter", help="Cover letter text or path"
    ),
    salary: Optional[str] = typer.Option(
        None, "--salary", help="Salary expectation (e.g. '$120,000')"
    ),
    location: Optional[str] = typer.Option(None, "--location", help="Your location (city, state)"),
    work_auth: Optional[str] = typer.Option(None, "--work-auth", help="Work authorization status"),
    years_exp: Optional[str] = typer.Option(None, "--years-exp", help="Years of experience"),
    education: Optional[str] = typer.Option(None, "--education", help="Highest education level"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for fill data (JSON)"
    ),
    generate_script: Optional[Path] = typer.Option(
        None, "--generate-script", "-g", help="Generate Playwright Python script"
    ),
    generate_curl: Optional[Path] = typer.Option(
        None, "--generate-curl", help="Generate curl commands script"
    ),
    use_chrome: bool = typer.Option(
        False, "--use-chrome", help="Use system Chrome with your profile (cookies, sessions)"
    ),
    chrome_profile: Optional[str] = typer.Option(
        None, "--chrome-profile", help="Path to Chrome user data directory"
    ),
    live: bool = typer.Option(
        False, "--live", help="Live mode: open browser, fill interactively, review before submit"
    ),
):
    """🤖 Auto-fill web forms — analyze forms and match to your profile data.

    Examples:
        spider autofill https://jobs.lever.co/company/position --profile me.json
        spider autofill https://example.com/apply \\
            --first-name "Candidate" --last-name "Example" \\
            --email "candidate@example.com" \\
            --linkedin "https://linkedin.com/in/example-candidate" \\
            --salary "R$ 15.000" --years-exp "5"
        spider autofill https://example.com/apply --profile me.json --generate-script fill.py
    """

    console.print("\n[bold]🤖 Form Auto-Filler[/]\n")
    console.print(f"Target: [cyan]{url}[/]")

    async def run():
        # Live mode: interactive browser fill
        if live:
            console.print("[cyan]🕹️  Live mode — opening browser for interactive fill[/]")
            live_profile = (
                AutoFillProfile.from_json(str(profile_json)) if profile_json else AutoFillProfile()
            )
            if first_name:
                live_profile.first_name = first_name
            if last_name:
                live_profile.last_name = last_name
            if full_name:
                live_profile.full_name = full_name
            if email:
                live_profile.email = email
            if phone:
                live_profile.phone = phone
            if linkedin:
                live_profile.linkedin_url = linkedin
            if github:
                live_profile.github_url = github
            if portfolio:
                live_profile.portfolio_url = portfolio
            if location:
                live_profile.location = location
            if salary:
                live_profile.salary_expectation = salary
            if work_auth:
                live_profile.work_authorization = work_auth
            if years_exp:
                live_profile.years_experience = years_exp
            if education:
                live_profile.highest_education = education
            if resume:
                live_profile.resume_path = str(resume)
            if cover_letter:
                cp = Path(cover_letter)
                live_profile.cover_letter_text = cp.read_text() if cp.exists() else cover_letter
            success = await live_fill_url(
                url,
                live_profile,
                use_chrome=use_chrome,
                chrome_user_data_dir=str(chrome_profile) if chrome_profile else None,
            )
            if success:
                console.print("\n[green]✓ Live fill completed and submitted![/]")
            else:
                console.print("\n[yellow]Live fill ended without submission.[/]")
            return

        # Build profile
        if profile_json:
            profile = AutoFillProfile.from_json(str(profile_json))
            console.print(f"[green]Loaded profile from {profile_json}[/]")
        else:
            profile = AutoFillProfile()

        # Override with CLI args
        if first_name:
            profile.first_name = first_name
        if last_name:
            profile.last_name = last_name
        if full_name:
            profile.full_name = full_name
        if email:
            profile.email = email
        if phone:
            profile.phone = phone
        if linkedin:
            profile.linkedin_url = linkedin
        if github:
            profile.github_url = github
        if portfolio:
            profile.portfolio_url = portfolio
        if location:
            profile.location = location
        if salary:
            profile.salary_expectation = salary
        if work_auth:
            profile.work_authorization = work_auth
        if years_exp:
            profile.years_experience = years_exp
        if education:
            profile.highest_education = education
        if resume:
            profile.resume_path = str(resume)
        if cover_letter:
            # Check if it's a file path
            cover_path = Path(cover_letter)
            if cover_path.exists():
                profile.cover_letter_text = cover_path.read_text()
            else:
                profile.cover_letter_text = cover_letter

        # Fetch and analyze
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text

        filler = FormAutoFiller(profile)
        results = await filler.analyze_and_fill(url, html)

        if not results:
            console.print("[yellow]No forms found on this page.[/]")
            return

        # Display results
        for i, result in enumerate(results):
            purpose = result.get("form_purpose") or "unknown"
            platform = result.get("platform") or "generic"
            coverage = result.get("fill_coverage", 0) * 100
            fill_data = result.get("fill_data", {})
            fill_items = result.get("fill_results", [])
            conf_summary = result.get("confidence_summary", {})

            console.print(f"\n[bold]Form {i + 1}:[/] [cyan]{purpose}[/] [dim]({platform})[/]")
            console.print(f"  Action: [dim]{result.get('form_action', 'N/A')[:80]}[/]")
            console.print(f"  Method: {result.get('form_method', 'get').upper()}")

            # Confidence summary bar
            high_c = conf_summary.get("high", 0)
            med_c = conf_summary.get("medium", 0)
            low_c = conf_summary.get("low", 0)
            none_c = conf_summary.get("none", 0)
            total_f = sum([high_c, med_c, low_c, none_c])
            bars = []
            if high_c:
                bars.append(f"[green]{'█' * high_c}[/]")
            if med_c:
                bars.append(f"[yellow]{'█' * med_c}[/]")
            if low_c:
                bars.append(f"[red]{'█' * low_c}[/]")
            if none_c:
                bars.append(f"[dim]{'░' * none_c}[/]")
            bar_str = "".join(bars)
            console.print(f"  Confidence: {bar_str}")
            console.print(
                f"  [green]● {high_c} high[/]  [yellow]● {med_c} medium[/]  [red]● {low_c} low[/]  [dim]● {none_c} none[/]"
            )

            if result.get("has_captcha"):
                console.print("  [red]⚠️  CAPTCHA detected[/]")
            if result.get("has_file_upload"):
                console.print("  [yellow]📎 File upload field(s) detected[/]")

            if fill_items:
                console.print("\n  [bold]Field Details:[/]")
                for f in fill_items:
                    name = f.get("field_name", "?")
                    label = f.get("field_label")
                    conf = f.get("confidence", 0)
                    value = f.get("value")
                    matched_by = f.get("matched_by", "?")

                    if conf >= 0.8:
                        icon = "🟢"
                    elif conf >= 0.5:
                        icon = "🟡"
                    elif conf >= 0.3:
                        icon = "🔴"
                    else:
                        icon = "⚫"

                    label_str = f"({label})" if label else ""
                    val_str = f"→ [cyan]{value[:50]}[/]" if value else "→ [dim](empty)[/]"
                    console.print(
                        f"    {icon} [bold]{name}[/] {label_str} {val_str} [dim]({matched_by}, {conf:.0%})[/]"
                    )

        # Save output
        if output:
            import json

            with open(output, "w") as f:
                json.dump(results, f, indent=2, default=str)
            console.print(f"\n[green]📄 Fill data saved to: {output}[/]")

        # Generate Playwright script
        if generate_script:
            script = filler.generate_playwright_script(
                url, results, use_chrome, str(chrome_profile) if chrome_profile else None
            )
            generate_script.write_text(script)
            console.print(f"[green]🎭 Playwright script: {generate_script}[/]")
            if use_chrome:
                console.print("    [cyan]Using system Chrome with your profile[/]")
            console.print(f"    Run with: python {generate_script}")

        # Generate curl commands
        if generate_curl:
            curl_script = filler.generate_curl_commands(results)
            generate_curl.write_text(curl_script)
            console.print(f"[green]📡 Curl script: {generate_curl}[/]")
            console.print(f"    Run with: bash {generate_curl}")

        # Quick tip
        if not output and not generate_script and not generate_curl:
            console.print(
                f"\n[dim]Tip: Use --output to save fill data, --generate-script for Playwright, or --generate-curl for curl[/]"
            )

    asyncio.run(run())
    console.print("\n[green]✓ Auto-fill analysis complete[/]")


@web_app.command("dirs")
def web_dirs(
    url: str = typer.Argument(..., help="Base URL to brute-force"),
    wordlist: Optional[str] = typer.Option(
        None, "--wordlist", "-w", help="Wordlist name (common_dirs, api_paths) or path"
    ),
    extensions: Optional[str] = typer.Option(
        None, "--extensions", "-e", help="Extensions to try (comma-separated)"
    ),
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
    resources: str = typer.Option(
        "all", "--resources", "-r", help="Resources to check (all or comma-separated)"
    ),
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
                for r in found_resources
                if r.exists
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
                snapshot.archive_url[:70] + "..."
                if len(snapshot.archive_url) > 70
                else snapshot.archive_url,
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
    domain: str = typer.Argument(
        None, help="Company domain to scan (e.g. stripe.com). If omitted, searches job boards."
    ),
    skills: Optional[str] = typer.Option(
        None, "--skills", "-s", help="Your skills (comma-separated, e.g. 'python,rust,nix')"
    ),
    titles: Optional[str] = typer.Option(
        None, "--titles", "-t", help="Desired job titles (comma-separated)"
    ),
    remote: str = typer.Option(
        "any",
        "--remote",
        "-r",
        help="Remote preference: remote_only, remote_preferred, hybrid_ok, any",
    ),
    min_salary: Optional[float] = typer.Option(
        None, "--min-salary", help="Minimum salary (e.g. 80000)"
    ),
    currency: str = typer.Option(
        "USD", "--currency", "-c", help="Preferred currency: USD, EUR, BRL, GBP"
    ),
    seniority: Optional[str] = typer.Option(
        None, "--seniority", help="Target seniority: junior, mid, senior, staff, principal"
    ),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (JSON)"),
    save_db: Optional[Path] = typer.Option(
        None, "--save-db", help="Save to SQLite database for tracking"
    ),
    max_jobs: int = typer.Option(100, "--max", "-m", help="Maximum jobs to return"),
    include_ats: bool = typer.Option(
        True, "--ats/--no-ats", help="Scan ATS platforms (Greenhouse, Lever, Ashby)"
    ),
    include_boards: bool = typer.Option(
        True, "--boards/--no-boards", help="Scan job boards (RemoteOK, WWR, HN)"
    ),
):
    """💼 Professional job hunt — scan ATS platforms, job boards, and career pages.

    Examples:
        spider job-hunt stripe.com                    # Scan a company's ATS
        spider job-hunt --skills 'python,rust,nix'    # Search job boards by skills
        spider job-hunt stripe.com --skills 'rust' --remote remote_only --min-salary 120000
        spider job-hunt --skills 'go,k8s' --save-db jobs.db  # Save results for tracking
    """

    console.print("\n[bold]💼 Professional Job Hunt[/]\n")

    # Build profile from CLI args
    profile = None
    skill_list: list[str] = []
    title_list: list[str] = []
    if skills or titles or remote != "any" or min_salary or seniority:
        skill_list = [s.strip() for s in skills.split(",")] if skills else []
        title_list = [t.strip() for t in titles.split(",")] if titles else []

        try:
            remote_pref = PreferredRemote(remote)
        except ValueError:
            console.print(f"[yellow]Invalid remote preference '{remote}'. Using 'any'.[/]")
            remote_pref = PreferredRemote.ANY

        target_seniorities = []
        if seniority:
            try:
                target_seniorities = [Seniority(seniority)]
            except ValueError:
                console.print(f"[yellow]Invalid seniority '{seniority}'. Ignoring.[/]")

        profile = JobSeekerProfile(
            skills=skill_list,
            desired_titles=title_list,
            preferred_remote=remote_pref,
            min_salary=min_salary,
            preferred_currency=currency,
            target_seniority=target_seniorities,
        )

    async def run():
        all_jobs: list[JobOpportunity] = []

        # Strategy 1: Company-specific ATS scan
        if domain:
            console.print(f"[yellow]🔍 Scanning {domain} for career pages & ATS listings...[/]\n")
            discoverer = CareerPageDiscoverer()
            career_urls = await discoverer.discover(domain, check_ats=include_ats)

            if career_urls:
                console.print(f"[green]Found {len(career_urls)} career sources:[/]")
                for u in career_urls[:10]:
                    console.print(f"  • {u}")
            else:
                console.print(
                    "[yellow]No career pages found via discovery. Trying ATS directly...[/]"
                )

            if include_ats:
                console.print(
                    "\n[yellow]📡 Querying ATS platforms (Greenhouse, Lever, Ashby)...[/]"
                )
                ats_jobs = await discover_and_scrape(domain, max_per_source=max_jobs // 3)
                all_jobs.extend(ats_jobs)
                console.print(f"[green]  → {len(ats_jobs)} jobs from ATS platforms[/]")

        # Strategy 2: Job board aggregation
        if include_boards and (not domain or skills):
            console.print("\n[yellow]🌐 Searching job boards (RemoteOK, WeWorkRemotely, HN)...[/]")
            search_terms = title_list if titles else None
            board_jobs = await scrape_all_boards(
                skills=skill_list if skills else None,
                search_terms=search_terms,
                max_per_source=max_jobs // 3,
                include_hn=include_boards,
                include_remoteok=include_boards,
                include_wwr=include_boards,
            )
            all_jobs.extend(board_jobs)
            console.print(f"[green]  → {len(board_jobs)} jobs from public boards[/]")

        # Deduplicate
        seen_ids = set()
        unique_jobs = []
        for j in all_jobs:
            if j.id not in seen_ids:
                seen_ids.add(j.id)
                unique_jobs.append(j)
        all_jobs = unique_jobs

        console.print(f"\n[bold]Total unique jobs found: {len(all_jobs)}[/]\n")

        if not all_jobs:
            console.print(
                "[yellow]No jobs found. Try different skills or a specific company domain.[/]"
            )
            return

        # Score with profile if provided
        if profile:
            console.print("[yellow]🎯 Matching jobs against your profile...[/]")
            all_jobs = match_jobs(all_jobs, profile, min_score=0.0)
            all_jobs.sort(key=lambda j: j.score, reverse=True)

        # Display results
        display_jobs = all_jobs[:max_jobs]

        table = Table(title=f"💼 Job Opportunities ({len(display_jobs)} shown)")
        table.add_column("#", style="dim")
        table.add_column("Sc", style="bold cyan")
        table.add_column("Title", style="green")
        table.add_column("Company", style="white")
        table.add_column("Location", style="dim")
        table.add_column("Stk", style="yellow")
        table.add_column("Source", style="magenta")
        table.add_column("Apply URL", style="dim")

        for i, job in enumerate(display_jobs, 1):
            apply_url = (job.apply_url or job.source_url)[:55]
            table.add_row(
                str(i),
                f"{job.score:.0f}" if job.score else "-",
                job.title[:50] if job.title else "Untitled",
                job.company[:20] if job.company else "-",
                job.location[:15] if job.location else "-",
                ", ".join(job.tech_stack[:3]) if job.tech_stack else "-",
                job.source.value,
                apply_url if apply_url else "-",
            )

        console.print(table)

        # Salary summary
        with_salary = [j for j in display_jobs if j.salary and j.salary.midpoint]
        if with_salary:
            console.print(f"\n[bold]💰 {len(with_salary)} jobs with salary data[/]")

        # Save to database
        if save_db:
            console.print(f"\n[yellow]💾 Saving to database: {save_db}[/]")
            storage = JobStorage(save_db)
            saved = await storage.save_jobs_batch(display_jobs)
            if profile:
                await storage.save_profile(profile)
            await storage.close()
            console.print(f"[green]  → {saved} jobs saved to {save_db}[/]")
            console.print(
                f"[green]  → Use 'spider job-track --db {save_db}' to manage applications[/]"
            )

        # Save to JSON
        if output:
            import json

            data = [j.to_dict() for j in display_jobs]
            with open(output, "w") as f:
                json.dump(data, f, indent=2, default=str)
            console.print(f"\n[green]📄 Exported to: {output}[/]")

        # Show top job detail
        if display_jobs:
            best = display_jobs[0]
            console.print(f"\n[bold]🏆 Top Match:[/]")
            console.print(f"  [green]{best.title}[/] @ [cyan]{best.company}[/]")
            if best.apply_url:
                console.print(f"  🔗 [dim]{best.apply_url}[/]")
            if best.salary:
                console.print(f"  💰 {best.salary.display}")
            if best.match_details:
                skills_info = best.match_details.get("skills", {})
                matched = skills_info.get("matched", [])
                if matched:
                    console.print(f"  ✅ Skills matched: {', '.join(matched)}")

    asyncio.run(run())
    console.print("\n[green]✓ Job hunt complete[/]")


@app.command("job-track")
def job_track(
    db: Path = typer.Option("jobs.db", "--db", "-d", help="SQLite database path"),
    job_id: Optional[str] = typer.Option(None, "--id", "-i", help="Job ID to update"),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="New status: saved, applied, phone_screen, technical, onsite, offer, accepted, rejected, withdrawn",
    ),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Add notes to application"),
    list_status: Optional[str] = typer.Option(
        None, "--list", "-l", help="List applications by status"
    ),
    summary: bool = typer.Option(False, "--summary", help="Show pipeline summary"),
    export_json: Optional[Path] = typer.Option(
        None, "--export", "-e", help="Export applications to JSON"
    ),
):
    """📋 Track job applications through the hiring pipeline.

    Examples:
        spider job-track --summary                    # Pipeline overview
        spider job-track --list applied                # Show applied jobs
        spider job-track --id abc123 --status applied  # Mark as applied
        spider job-track --id abc123 --status interview --notes "Scheduled for Friday"
        spider job-track --export apps.json            # Export all applications
    """

    console.print("\n[bold]📋 Application Tracker[/]\n")

    async def run():
        tracker = ApplicationTracker(db_path=str(db))

        try:
            if summary:
                report = await tracker.pipeline_summary()
                console.print(report)

            elif list_status:
                try:
                    status_enum = ApplicationStatus(list_status)
                except ValueError:
                    console.print(f"[red]Invalid status: {list_status}[/]")
                    return

                apps = await tracker.storage.get_applications(status=status_enum, limit=50)
                if not apps:
                    console.print(f"[yellow]No applications with status '{list_status}'[/]")
                else:
                    table = Table(title=f"Applications: {list_status} ({len(apps)})")
                    table.add_column("Job ID", style="dim")
                    table.add_column("Title", style="green")
                    table.add_column("Company", style="cyan")
                    table.add_column("Score", style="yellow")
                    table.add_column("Updated", style="dim")
                    for app in apps:
                        table.add_row(
                            app.get("job_id", "")[:12],
                            app.get("title", "-")[:50],
                            app.get("company", "-")[:20],
                            f"{app.get('score', 0):.0f}",
                            app.get("updated_at", "-")[:16],
                        )
                    console.print(table)

            elif job_id and status:
                try:
                    status_enum = ApplicationStatus(status)
                except ValueError:
                    console.print(f"[red]Invalid status: {status}[/]")
                    console.print("Valid: " + ", ".join(s.value for s in ApplicationStatus))
                    return

                ok = await tracker.advance_status(job_id, status_enum, notes or "")
                if ok:
                    console.print(f"[green]✓ Job {job_id} → {status}[/]")
                    if notes:
                        console.print(f"  Notes: {notes}")
                else:
                    console.print(f"[red]Failed to update job {job_id}[/]")

            elif job_id and notes:
                ok = await tracker.add_notes(job_id, notes)
                if ok:
                    console.print(f"[green]✓ Notes added to {job_id}[/]")

            elif export_json:
                path = await tracker.export_applications(str(export_json))
                console.print(f"[green]✓ Exported to {path}[/]")

            else:
                # Default: show summary
                report = await tracker.pipeline_summary()
                console.print(report)

        finally:
            await tracker.close()

    asyncio.run(run())
    console.print("\n[green]✓ Done[/]")


@app.command("job-profile")
def job_profile(
    db: Path = typer.Option("jobs.db", "--db", "-d", help="SQLite database path"),
    skills: Optional[str] = typer.Option(
        None, "--skills", "-s", help="Your skills (comma-separated)"
    ),
    titles: Optional[str] = typer.Option(None, "--titles", "-t", help="Desired job titles"),
    remote: Optional[str] = typer.Option(None, "--remote", "-r", help="Remote preference"),
    min_salary: Optional[float] = typer.Option(None, "--min-salary", help="Minimum salary"),
    currency: str = typer.Option("USD", "--currency", "-c", help="Currency"),
    show: bool = typer.Option(False, "--show", help="Show current profile"),
    from_resume: Optional[Path] = typer.Option(
        None, "--from-resume", help="Parse resume PDF/DOCX/TXT and populate profile"
    ),
):
    """👤 Manage your job seeker profile for better matching.

    Examples:
        spider job-profile --show
        spider job-profile --skills 'python,rust,nix,kubernetes' --titles 'Senior Backend Engineer'
        spider job-profile --remote remote_only --min-salary 120000 --currency USD
        spider job-profile --from-resume curriculo.pdf
    """

    console.print("\n[bold]👤 Job Seeker Profile[/]\n")

    async def run():
        storage = JobStorage(db)

        try:
            # Parse resume if provided
            if from_resume:
                suffix = from_resume.suffix.lower() or "unknown type"
                console.print(f"[yellow]📄 Parsing resume file ({suffix})[/]")
                try:
                    resume_data = parse_resume(str(from_resume))
                    console.print(resume_data.summary())

                    # Populate profile from resume
                    profile = resume_data.to_job_seeker_profile()
                    autofill_p = resume_data.to_autofill_profile()

                    # Save both profiles
                    await storage.save_profile(profile)

                    # Also save AutoFillProfile as JSON for form filling
                    import json

                    af_json_path = Path(str(db)).with_suffix(".autofill.json")
                    af_json_path.write_text(json.dumps(autofill_p.to_dict(), indent=2))

                    console.print("\n[green]✓ Profile populated from resume![/]")
                    console.print(f"  Skills: {', '.join(profile.skills[:15])}")
                    console.print(f"  Experience: {profile.years_experience:.1f} years")
                    console.print(f"  Seniority: {profile.current_seniority.value}")

                    # Also save matching profile
                    if profile.desired_titles:
                        console.print(f"  Titles: {', '.join(profile.desired_titles)}")

                    console.print(
                        "\n[dim]Run 'spider job hunt --skills ...' to find matching jobs[/]"
                    )
                    return
                except Exception as e:
                    console.print(f"[red]Failed to parse resume: {e}[/]")
                    return

            if show or not any([skills, titles, remote, min_salary]):
                profile = await storage.load_profile()
                if profile:
                    console.print("[bold]Current Profile:[/]")
                    console.print(
                        f"  Skills: {', '.join(profile.skills) if profile.skills else '(not set)'}"
                    )
                    console.print(
                        f"  Titles: {', '.join(profile.desired_titles) if profile.desired_titles else '(not set)'}"
                    )
                    console.print(f"  Remote: {profile.preferred_remote.value}")
                    console.print(
                        f"  Min Salary: {profile.preferred_currency} {profile.min_salary or '(not set)'}"
                    )
                    console.print(
                        f"  Target Seniority: {[s.value for s in profile.target_seniority] if profile.target_seniority else '(not set)'}"
                    )
                else:
                    console.print(
                        "[yellow]No profile saved yet. Set one with --skills, --titles, etc.[/]"
                    )
                return

            # Build/update profile
            existing = await storage.load_profile()
            profile = existing or JobSeekerProfile()

            if skills:
                profile.skills = [s.strip() for s in skills.split(",")]
            if titles:
                profile.desired_titles = [t.strip() for t in titles.split(",")]
            if remote:
                try:
                    profile.preferred_remote = PreferredRemote(remote)
                except ValueError:
                    console.print(f"[yellow]Invalid remote preference: {remote}[/]")
            if min_salary is not None:
                profile.min_salary = min_salary
            if currency:
                profile.preferred_currency = currency

            await storage.save_profile(profile)
            console.print("[green]✓ Profile saved![/]")
            console.print(f"  Skills: {', '.join(profile.skills)}")
            console.print(f"  Titles: {', '.join(profile.desired_titles)}")
            console.print(f"  Remote: {profile.preferred_remote.value}")
            console.print(
                f"  Min Salary: {profile.preferred_currency} {profile.min_salary or '(not set)'}"
            )

            # Offer to re-match existing jobs
            job_count = await storage.count_jobs()
            if job_count > 0:
                console.print(f"\n[yellow]📊 You have {job_count} jobs in the database.[/]")
                console.print(
                    f"[yellow]   Run 'spider job-track --summary' to see your pipeline.[/]"
                )

        finally:
            await storage.close()

    asyncio.run(run())
    console.print("\n[green]✓ Done[/]")


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
    console.print("\n[bold]🕷️ SpiderNix Configuration Presets[/]\n")

    presets_info = list_presets()

    table = Table(title="Available Presets", show_header=True, header_style="bold cyan")
    table.add_column("Preset", style="cyan", width=15)
    table.add_column("Description", style="white")

    for name, description in presets_info.items():
        table.add_row(name, description)

    console.print(table)
    console.print("\n[dim]Usage: spider advanced-crawl --preset <name>[/]")


@app.command()
def advanced_crawl(
    url: str = typer.Argument(..., help="URL to crawl"),
    pages: int = typer.Option(10, "--pages", "-p", help="Max pages to crawl"),
    preset: Optional[str] = typer.Option(
        None, "--preset", help="Config preset (run 'presets' to see options)"
    ),
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
    console.print(
        "[cyan]Features: Rate Limiting ✓ | Circuit Breaker ✓ | Deduplication ✓ | Monitoring ✓[/]\n"
    )

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
                    if result and hasattr(result, "status_code"):
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
        console.print("\n[cyan]Generating HTML report...[/]")
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

    console.print("\n[bold]📊 Generating HTML Report[/]\n")

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
    screenshot: Optional[Path] = typer.Option(
        None, "--screenshot", "-s", help="Save screenshot path"
    ),
    headless: bool = typer.Option(True, "--headless", help="Run browser headless"),
    use_proxy: bool = typer.Option(True, "--proxy", help="Use network OPSEC proxy"),
    vision_model: str = typer.Option(
        "llava-v1.5-7b-q4", "--model", "-m", help="Vision model to use"
    ),
    iou_threshold: float = typer.Option(0.5, "--iou", help="IoU threshold for fusion (0-1)"),
):
    """
    🤖 Multimodal extraction - Vision + DOM fusion for CSS-independent scraping.

    Uses vision AI to detect elements visually, then fuses with DOM for
    high-confidence extractions resilient to CSS class changes.

    Example:
        spider recon multimodal https://example.com
        spider recon multimodal https://example.com --model llava-v1.5-7b-q4
        spider recon multimodal https://example.com --iou 0.7 --proxy
    """
    import json

    from .extraction import MultimodalExtractor

    console.print("\n[bold]🤖 Multimodal Extraction[/]\n")
    console.print(f"Target: [cyan]{url}[/]")
    console.print(f"Vision Model: [yellow]{vision_model}[/]")
    console.print(f"IoU Threshold: [yellow]{iou_threshold}[/]")
    console.print(
        f"Network Proxy: [{'green' if use_proxy else 'red'}]{'enabled' if use_proxy else 'disabled'}[/]\n"
    )

    async def run():
        extractor = MultimodalExtractor(iou_threshold=iou_threshold, vision_model=vision_model)

        try:
            # Extract from URL
            console.print("[cyan]→[/] Extracting elements...")
            result = await extractor.extract_from_url(
                url, headless=headless, use_network_proxy=use_proxy
            )

            # Save results
            with open(output, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

            # Print summary
            console.print("\n[bold green]✓ Extraction Complete[/]\n")

            # Results table
            table = Table(title="Extraction Results")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="yellow")

            table.add_row("URL", url)
            table.add_row("Total Elements", str(result.total_elements))
            table.add_row(
                "Fused (High Conf)", f"{result.fused_count} ({result.fusion_success_rate:.1f}%)"
            )
            table.add_row("Vision Only", str(result.vision_only_count))
            table.add_row("DOM Only", str(result.dom_only_count))
            table.add_row("Resilient Elements", str(len(result.get_resilient_elements())))
            table.add_row("Average IoU", f"{result.average_iou:.3f}")
            table.add_row("Extraction Time", f"{result.extraction_time_ms:.0f}ms")
            table.add_row("Model Inference", f"{result.model_inference_time_ms:.0f}ms")
            table.add_row("Fusion Time", f"{result.fusion_time_ms:.0f}ms")

            console.print(table)

            # Elements breakdown
            console.print("\n[bold]Detected Elements:[/]")
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
