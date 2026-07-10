"""
ATS (Applicant Tracking System) Platform Scrapers.

Supports: Greenhouse, Lever, Ashby, Workday, BambooHR, and generic career page discovery.
Each scraper knows the URL structure of these platforms and can extract structured job data.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from dataclasses import dataclass, field

import httpx

from spider_nix.intel.jobs import (
    JobOpportunity,
    JobSource,
    extract_employment_type,
    extract_remote_policy,
    extract_salary,
    extract_seniority,
    extract_tech_stack,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ATS URL patterns
# ---------------------------------------------------------------------------

ATS_PATTERNS: dict[str, list[str]] = {
    "greenhouse": [
        "boards.greenhouse.io/{company}",
        "boards.greenhouse.io/embed/job_board",
    ],
    "lever": [
        "jobs.lever.co/{company}",
    ],
    "ashby": [
        "jobs.ashbyhq.com/{company}",
    ],
    "bamboohr": [
        "{company}.bamboohr.com/careers",
        "{company}.bamboohr.com/jobs",
    ],
    "workday": [
        "{company}.wd1.myworkdayjobs.com",
        "{company}.wd5.myworkdayjobs.com",
    ],
}


@dataclass
class ATSScraperResult:
    """Result from an ATS scraper run."""

    source: JobSource
    company_domain: str
    jobs: list[JobOpportunity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    raw_responses: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class BaseATSScraper:
    """Base scraper with shared HTTP logic."""

    def __init__(self, client: httpx.AsyncClient | None = None, timeout: float = 30.0):
        self._client = client
        self._owns_client = client is None
        self.timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/html, */*",
                },
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _fetch_json(self, url: str) -> dict | list | None:
        """Fetch a URL and parse as JSON."""
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch a URL and return HTML text."""
        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------


class GreenhouseScraper(BaseATSScraper):
    """
    Greenhouse board scraper.

    Greenhouse has a public JSON API at:
        https://boards.greenhouse.io/{company}/embed/job_board?content=true
    or
        https://boards.greenhouse.io/{company}
    """

    BASE = "https://boards.greenhouse.io"

    async def scrape(self, company: str) -> ATSScraperResult:
        """
        Scrape all jobs from a Greenhouse board.

        Args:
            company: Company slug (e.g. 'stripe', 'airbnb')
        """
        result = ATSScraperResult(
            source=JobSource.GREENHOUSE,
            company_domain=company,
        )

        # Try the embed JSON API first (most reliable)
        api_url = f"{self.BASE}/{company}/embed/job_board?content=true"
        data = await self._fetch_json(api_url)

        if data and isinstance(data, dict):
            departments = data.get("departments", [])
            jobs_data = []
            for dept in departments:
                jobs_data.extend(dept.get("jobs", []))

            for job in jobs_data:
                try:
                    result.jobs.append(self._parse_greenhouse_job(job, company))
                except Exception as e:
                    result.errors.append(f"Parse error: {e}")

        if not result.jobs:
            # Fallback: scrape the HTML page
            html_url = f"{self.BASE}/{company}"
            html = await self._fetch_html(html_url)
            if html:
                result.jobs.extend(self._parse_greenhouse_html(html, company))

        return result

    def _parse_greenhouse_job(self, job: dict, company: str) -> JobOpportunity:
        """Parse a single Greenhouse JSON job object."""
        title = job.get("title", "")
        location_info = job.get("location", {})
        location = (
            location_info.get("name", "") if isinstance(location_info, dict) else str(location_info)
        )

        # Build description from metadata fields
        metadata = job.get("metadata", [])
        desc_parts = []
        for m in metadata:
            if (
                m.get("name") == "Job Description"
                or m.get("name") == "Responsibilities"
                or m.get("name") == "Requirements"
            ):
                desc_parts.append(m.get("value", ""))

        description = "\n\n".join(desc_parts)
        if not description:
            description = job.get("content", "")

        # Extract HTML from description
        description = self._strip_html(description)

        apply_url = job.get("absolute_url", "")
        if apply_url and not apply_url.startswith("http"):
            apply_url = f"{self.BASE}{apply_url}"

        source_url = apply_url

        job_obj = JobOpportunity(
            source=JobSource.GREENHOUSE,
            source_url=source_url,
            apply_url=apply_url,
            title=title,
            company=job.get("company_name", company).title(),
            location=location,
            description=description,
            tech_stack=extract_tech_stack(description + " " + title),
            seniority=extract_seniority(title + " " + description),
            remote_policy=extract_remote_policy(location + " " + description),
            salary=extract_salary(description),
            raw_data=job,
        )

        return job_obj

    def _parse_greenhouse_html(self, html: str, company: str) -> list[JobOpportunity]:
        """Fallback: parse Greenhouse HTML page for job listings."""
        jobs: list[JobOpportunity] = []
        # Look for job postings in the HTML
        pattern = re.compile(
            r'<a[^>]*href="(/[^"]*jobs/[^"]*)"[^>]*>\s*'
            r"(?:<[^>]*>)*\s*([^<]+)\s*(?:</[^>]*>)*\s*"
            r'(?:<[^>]*class="[^"]*location[^"]*"[^>]*>([^<]*)</[^>]*>)?',
            re.IGNORECASE | re.DOTALL,
        )

        for match in pattern.finditer(html):
            path = match.group(1)
            title = match.group(2).strip() if match.group(2) else ""
            location = match.group(3).strip() if match.group(3) else ""

            apply_url = f"{self.BASE}{path}"

            jobs.append(
                JobOpportunity(
                    source=JobSource.GREENHOUSE,
                    source_url=apply_url,
                    apply_url=apply_url,
                    title=title,
                    company=company.title(),
                    location=location,
                    tech_stack=extract_tech_stack(title),
                    seniority=extract_seniority(title),
                    remote_policy=extract_remote_policy(location),
                )
            )
        return jobs

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags from text."""
        clean = re.compile(r"<[^>]+>")
        text = clean.sub(" ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------


class LeverScraper(BaseATSScraper):
    """
    Lever job board scraper.

    Lever has a public JSON API at:
        https://jobs.lever.co/{company}?format=json
    """

    BASE = "https://jobs.lever.co"

    async def scrape(self, company: str) -> ATSScraperResult:
        result = ATSScraperResult(
            source=JobSource.LEVER,
            company_domain=company,
        )

        # Lever has a nice JSON API
        api_url = f"{self.BASE}/{company}?format=json"
        data = await self._fetch_json(api_url)

        if isinstance(data, list):
            for job in data:
                try:
                    result.jobs.append(self._parse_lever_job(job, company))
                except Exception as e:
                    result.errors.append(f"Parse error: {e}")
        elif isinstance(data, dict):
            # Some Lever boards return a dict with a 'postings' key
            postings = data.get("postings", data.get("jobs", []))
            for job in postings:
                try:
                    result.jobs.append(self._parse_lever_job(job, company))
                except Exception as e:
                    result.errors.append(f"Parse error: {e}")

        return result

    def _parse_lever_job(self, job: dict, company: str) -> JobOpportunity:
        """Parse a single Lever JSON job object."""
        title = job.get("text", job.get("title", ""))

        # Lever categories (team, location, commitment)
        categories = job.get("categories", {})
        location = categories.get("location", "") if isinstance(categories, dict) else ""
        team = categories.get("team", "") if isinstance(categories, dict) else ""
        commitment = categories.get("commitment", "") if isinstance(categories, dict) else ""

        # Build full description
        desc_parts = []
        lists = job.get("lists", [])
        for lst in lists:
            section_title = lst.get("text", "")
            content = lst.get("content", "")
            if section_title:
                desc_parts.append(f"{section_title}\n{content}")
            else:
                desc_parts.append(content)
        description = "\n\n".join(desc_parts)
        description = self._strip_html(description)

        apply_url = job.get("applyUrl", job.get("hostedUrl", ""))
        if apply_url and apply_url.startswith("/"):
            apply_url = f"{self.BASE}{apply_url}"

        additional = job.get("additional", "")
        full_text = f"{title} {team} {description} {additional}"

        return JobOpportunity(
            source=JobSource.LEVER,
            source_url=apply_url,
            apply_url=apply_url,
            title=title,
            company=company.title(),
            location=location,
            description=description,
            employment_type=extract_employment_type(commitment + " " + full_text),
            tech_stack=extract_tech_stack(full_text),
            seniority=extract_seniority(title + " " + full_text),
            remote_policy=extract_remote_policy(location + " " + full_text),
            salary=extract_salary(full_text),
            raw_data=job,
            requirements=self._extract_list_items(description, ["requirement", "qualification"]),
            responsibilities=self._extract_list_items(description, ["responsibilit", "what you"]),
            benefits=self._extract_list_items(description, ["benefit", "perk", "what we offer"]),
        )

    @staticmethod
    def _extract_list_items(text: str, keywords: list[str]) -> list[str]:
        """Extract bullet-point items after a keyword heading."""
        items: list[str] = []
        text_lower = text.lower()
        for kw in keywords:
            idx = text_lower.find(kw)
            if idx >= 0:
                # Find bullet items after this heading
                section = text[idx : idx + 3000]
                bullets = re.findall(r"[•\-\*\d+\.]\s*(.{10,200})", section)
                items.extend(b.strip() for b in bullets[:15])
        return items

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = re.compile(r"<[^>]+>")
        text = clean.sub(" ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Ashby
# ---------------------------------------------------------------------------


class AshbyScraper(BaseATSScraper):
    """
    Ashby job board scraper.

    Ashby has an API at:
        https://jobs.ashbyhq.com/{company}/api/jobs
    """

    BASE = "https://jobs.ashbyhq.com"

    async def scrape(self, company: str) -> ATSScraperResult:
        result = ATSScraperResult(
            source=JobSource.ASHBY,
            company_domain=company,
        )

        # Ashby API
        api_url = f"{self.BASE}/{company}/api/jobs"
        data = await self._fetch_json(api_url)

        if isinstance(data, dict):
            jobs_data = data.get("jobs", data.get("data", []))
            if isinstance(jobs_data, list):
                for job in jobs_data:
                    try:
                        result.jobs.append(self._parse_ashby_job(job, company))
                    except Exception as e:
                        result.errors.append(f"Parse error: {e}")

        return result

    def _parse_ashby_job(self, job: dict, company: str) -> JobOpportunity:
        title = job.get("title", "")
        location = job.get("location", "")
        if isinstance(location, dict):
            location = location.get("name", "")

        description = job.get("descriptionHtml", job.get("description", ""))
        description = self._strip_html(description)

        apply_url = job.get("applyUrl", job.get("url", ""))
        if apply_url and not apply_url.startswith("http"):
            apply_url = (
                f"{self.BASE}/{company}{apply_url}"
                if apply_url.startswith("/")
                else f"{self.BASE}/{company}/{apply_url}"
            )

        department = job.get("department", job.get("team", ""))
        full_text = f"{title} {department} {description}"

        return JobOpportunity(
            source=JobSource.ASHBY,
            source_url=apply_url,
            apply_url=apply_url,
            title=title,
            company=company.title(),
            location=location,
            description=description,
            tech_stack=extract_tech_stack(full_text),
            seniority=extract_seniority(full_text),
            remote_policy=extract_remote_policy(location + " " + full_text),
            salary=extract_salary(full_text),
            employment_type=extract_employment_type(full_text),
            raw_data=job,
        )

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = re.compile(r"<[^>]+>")
        text = clean.sub(" ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Career Page Discovery
# ---------------------------------------------------------------------------


class CareerPageDiscoverer:
    """
    Discover career/job pages for a company domain.

    Tries multiple strategies:
    1. Known ATS URL patterns (Greenhouse, Lever, Ashby, etc.)
    2. Common career subdomains
    3. Common career paths on main domain
    4. /careers, /jobs paths
    """

    CAREER_SUBDOMAINS = [
        "careers",
        "jobs",
        "join",
        "work",
        "talent",
        "people",
        "hr",
        "recruiting",
    ]

    CAREER_PATHS = [
        "/careers",
        "/jobs",
        "/join-us",
        "/work-with-us",
        "/about/careers",
        "/company/careers",
        "/careers/jobs",
        "/open-positions",
        "/openings",
        "/job-openings",
        "/current-openings",
        "/opportunities",
    ]

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def discover(
        self,
        domain: str,
        check_ats: bool = True,
        check_paths: bool = True,
        check_subdomains: bool = False,
    ) -> list[str]:
        """
        Discover career page URLs for a domain.

        Returns a list of URLs that are likely career/job pages.
        """
        urls: set[str] = set()
        clean_domain = domain.lower().replace("https://", "").replace("http://", "").rstrip("/")
        company_name = clean_domain.split(".")[0]

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            # Strategy 1: Known ATS patterns (most reliable)
            if check_ats:
                ats_tasks = []
                for platform, patterns in ATS_PATTERNS.items():
                    for pattern in patterns:
                        url = f"https://{pattern.format(company=company_name)}"
                        ats_tasks.append(self._check_url(client, url, platform))

                for coro in asyncio.as_completed(ats_tasks):
                    url = await coro
                    if url:
                        urls.add(url)

            # Strategy 2: Common career paths on main domain
            if check_paths:
                path_tasks = []
                for proto in ["https"]:
                    base = f"{proto}://{clean_domain}"
                    for path in self.CAREER_PATHS:
                        path_tasks.append(self._check_url(client, f"{base}{path}", "career_path"))
                    # Also try www subdomain
                    if not clean_domain.startswith("www."):
                        base_www = f"{proto}://www.{clean_domain}"
                        for path in self.CAREER_PATHS:
                            path_tasks.append(
                                self._check_url(client, f"{base_www}{path}", "career_path")
                            )

                for coro in asyncio.as_completed(path_tasks):
                    url = await coro
                    if url:
                        urls.add(url)

            # Strategy 3: Career subdomains (expensive, off by default)
            if check_subdomains:
                subdomain_tasks = []
                for sub in self.CAREER_SUBDOMAINS:
                    subdomain_tasks.append(
                        self._check_url(client, f"https://{sub}.{clean_domain}", "subdomain")
                    )
                for coro in asyncio.as_completed(subdomain_tasks):
                    url = await coro
                    if url:
                        urls.add(url)

        return sorted(urls)

    @staticmethod
    async def _check_url(client: httpx.AsyncClient, url: str, source: str) -> str | None:
        """Check if a URL is reachable. Returns the URL if yes, None otherwise."""
        try:
            resp = await client.head(url, timeout=10.0)
            if resp.status_code < 400:
                return url
        except Exception:
            # Try GET if HEAD fails
            with contextlib.suppress(Exception):
                resp = await client.get(url, timeout=10.0)
                if resp.status_code < 400:
                    return url
        return None


# ---------------------------------------------------------------------------
# Convenience: discover + scrape
# ---------------------------------------------------------------------------


async def discover_and_scrape(
    domain: str,
    max_per_source: int = 50,
    timeout: float = 30.0,
) -> list[JobOpportunity]:
    """
    High-level function: discover career pages and scrape jobs.

    Args:
        domain: Company domain (e.g., 'stripe.com')
        max_per_source: Maximum jobs to return per ATS source
        timeout: HTTP request timeout in seconds

    Returns:
        List of JobOpportunity objects
    """
    all_jobs: list[JobOpportunity] = []
    company_name = (
        domain.lower().replace("https://", "").replace("http://", "").rstrip("/").split(".")[0]
    )

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # Try all ATS scrapers in parallel
        scrapers: list[tuple[str, BaseATSScraper]] = [
            ("greenhouse", GreenhouseScraper(client)),
            ("lever", LeverScraper(client)),
            ("ashby", AshbyScraper(client)),
        ]

        async def run_scraper(name: str, scraper: BaseATSScraper) -> list[JobOpportunity]:
            try:
                result = await scraper.scrape(company_name)
                if result.errors:
                    logger.warning(f"{name} errors: {result.errors[:3]}")
                return result.jobs[:max_per_source]
            except Exception as e:
                logger.error(f"{name} scraper failed: {e}")
                return []

        tasks = [run_scraper(name, s) for name, s in scrapers]
        results = await asyncio.gather(*tasks)

        for jobs in results:
            all_jobs.extend(jobs)

    return all_jobs
