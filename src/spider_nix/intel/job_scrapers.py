"""
Job Board Aggregator Scrapers.

Scrapes popular tech job boards:
- RemoteOK (remoteok.com) — remote tech jobs with salary data
- We Work Remotely (weworkremotely.com) — largest remote work community
- Hacker News "Who is hiring?" — monthly thread, high-quality tech jobs
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from spider_nix.intel.jobs import (
    JobOpportunity,
    JobSource,
    Salary,
    extract_employment_type,
    extract_remote_policy,
    extract_salary,
    extract_seniority,
    extract_tech_stack,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RemoteOK
# ---------------------------------------------------------------------------


class RemoteOKScraper:
    """
    RemoteOK.com scraper.

    RemoteOK has a public JSON API:
        https://remoteok.com/api?tag=rust
        https://remoteok.com/api?tag=python

    Returns salary data, company info, tech stack — all structured.
    """

    BASE = "https://remoteok.com"
    API = "https://remoteok.com/api"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def scrape(
        self,
        tags: list[str] | None = None,
        search: str | None = None,
        max_jobs: int = 100,
    ) -> list[JobOpportunity]:
        """
        Scrape RemoteOK jobs.

        Args:
            tags: Job tags to filter (e.g. ['python', 'rust', 'devops'])
            search: Free-text search query
            max_jobs: Maximum jobs to return
        """
        jobs: list[JobOpportunity] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SpiderNix/0.2; +https://github.com/VoidNxSEC/spider-nix)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        ) as client:
            if tags:
                for tag in tags:
                    try:
                        url = f"{self.API}?tag={tag}"
                        resp = await client.get(url)
                        data = resp.json()
                        parsed = self._parse_remoteok(data, max_jobs // len(tags))
                        jobs.extend(parsed)
                    except Exception as e:
                        logger.warning(f"RemoteOK tag={tag} failed: {e}")
            elif search:
                try:
                    url = f"{self.API}?search={search}"
                    resp = await client.get(url)
                    data = resp.json()
                    jobs = self._parse_remoteok(data, max_jobs)
                except Exception as e:
                    logger.warning(f"RemoteOK search failed: {e}")
            else:
                # Fetch latest/jobs
                try:
                    resp = await client.get(self.API)
                    data = resp.json()
                    jobs = self._parse_remoteok(data, max_jobs)
                except Exception as e:
                    logger.warning(f"RemoteOK latest failed: {e}")

        return jobs

    def _parse_remoteok(self, data: list[dict], max_jobs: int) -> list[JobOpportunity]:
        """Parse RemoteOK JSON response."""
        jobs: list[JobOpportunity] = []

        for item in data:
            if len(jobs) >= max_jobs:
                break

            # Skip header row (RemoteOK returns legal notice as first element)
            if isinstance(item, dict) and item.get("legal"):
                continue

            if not isinstance(item, dict):
                continue

            try:
                title = item.get("position", "")
                company = item.get("company", "")
                location = item.get("location", "Remote")

                # RemoteOK tags
                tags = item.get("tags", [])
                tech_list = [
                    t for t in tags if t not in ("remote", "dev", "senior", "junior", "full-time")
                ] or []

                # Description
                description = item.get("description", "")
                description = self._strip_html(description)

                # Salary
                salary_min = item.get("salary_min")
                salary_max = item.get("salary_max")
                salary = None
                if salary_min or salary_max:
                    salary = Salary(
                        min_amount=float(salary_min) if salary_min else None,
                        max_amount=float(salary_max) if salary_max else None,
                        currency="USD",
                        period="yearly",
                    )

                # Apply URL
                apply_url = item.get("url", item.get("apply_url", ""))
                if apply_url and not apply_url.startswith("http"):
                    apply_url = f"{self.BASE}{apply_url}"

                # Date posted
                date_posted = None
                epoch = item.get("epoch", item.get("date"))
                if epoch:
                    try:
                        date_posted = datetime.fromtimestamp(
                            int(epoch), tz=timezone.utc
                        ).isoformat()
                    except (ValueError, TypeError):
                        pass

                full_text = f"{title} {description} {' '.join(tags)}"

                job = JobOpportunity(
                    source=JobSource.REMOTEOK,
                    source_url=apply_url,
                    apply_url=apply_url,
                    title=title,
                    company=company,
                    location=location,
                    description=description,
                    remote_policy=extract_remote_policy(location + " " + " ".join(tags)),
                    tech_stack=extract_tech_stack(full_text) or tech_list,
                    seniority=extract_seniority(title),
                    salary=salary or extract_salary(description),
                    date_posted=date_posted,
                    raw_data=item,
                )

                jobs.append(job)
            except Exception as e:
                logger.debug(f"RemoteOK parse error: {e}")

        return jobs

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = re.compile(r"<[^>]+>")
        text = clean.sub(" ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# We Work Remotely
# ---------------------------------------------------------------------------


class WeWorkRemotelyScraper:
    """
    We Work Remotely scraper.

    WWR has a public RSS feed and search:
        https://weworkremotely.com/categories/remote-programming-jobs
        https://weworkremotely.com/remote-jobs/search?term=python
    """

    BASE = "https://weworkremotely.com"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def scrape(
        self,
        categories: list[str] | None = None,
        search: str | None = None,
        max_jobs: int = 100,
    ) -> list[JobOpportunity]:
        """
        Scrape We Work Remotely jobs.

        Args:
            categories: Job categories (e.g. ['remote-programming-jobs', 'remote-devops-sysadmin-jobs'])
            search: Free-text search
            max_jobs: Max jobs to return
        """
        if categories is None:
            categories = ["remote-programming-jobs"]

        jobs: list[JobOpportunity] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SpiderNix/0.2)",
            },
            follow_redirects=True,
        ) as client:
            for category in categories:
                try:
                    url = (
                        f"{self.BASE}/categories/{category}.json"
                        if not search
                        else f"{self.BASE}/remote-jobs/search?term={search}"
                    )

                    resp = await client.get(url)
                    if "json" in resp.headers.get("content-type", ""):
                        data = resp.json()
                        parsed = self._parse_wwr_json(data, max_jobs)
                    else:
                        parsed = self._parse_wwr_html(resp.text, max_jobs)

                    jobs.extend(parsed)
                except Exception as e:
                    logger.warning(f"WWR {category} failed: {e}")

        return jobs[:max_jobs]

    def _parse_wwr_json(self, data: dict, max_jobs: int) -> list[JobOpportunity]:
        """Parse WWR JSON response."""
        jobs: list[JobOpportunity] = []
        listings = data.get("jobs", data.get("listings", []))

        for item in listings:
            if len(jobs) >= max_jobs:
                break
            try:
                title = item.get("title", "")
                company = item.get("company_name", item.get("company", ""))
                location = item.get("region", "Remote")
                description = self._strip_html(item.get("description", ""))
                apply_url = item.get("url", "")

                if apply_url and not apply_url.startswith("http"):
                    apply_url = f"{self.BASE}{apply_url}"

                full_text = f"{title} {description}"

                jobs.append(
                    JobOpportunity(
                        source=JobSource.WE_WORK_REMOTELY,
                        source_url=apply_url,
                        apply_url=apply_url,
                        title=title,
                        company=company,
                        location=location,
                        description=description,
                        remote_policy=extract_remote_policy(location),
                        tech_stack=extract_tech_stack(full_text),
                        seniority=extract_seniority(title),
                        salary=extract_salary(description),
                        raw_data=item,
                    )
                )
            except Exception as e:
                logger.debug(f"WWR parse error: {e}")

        return jobs

    def _parse_wwr_html(self, html: str, max_jobs: int) -> list[JobOpportunity]:
        """Fallback HTML parser for WWR."""
        jobs: list[JobOpportunity] = []

        # Find job listings in HTML
        listing_pattern = re.compile(
            r'<li[^>]*class="[^"]*feature[^"]*"[^>]*>.*?'
            r'<a[^>]*href="([^"]*)"[^>]*>\s*'
            r"(?:<[^>]*>)*\s*([^<]+)\s*(?:</[^>]*>)*\s*"
            r'(?:<[^>]*class="[^"]*company[^"]*"[^>]*>([^<]*))?'
            r".*?</li>",
            re.IGNORECASE | re.DOTALL,
        )

        for match in listing_pattern.finditer(html):
            if len(jobs) >= max_jobs:
                break
            try:
                path = match.group(1)
                title = match.group(2).strip()
                company = match.group(3).strip() if match.group(3) else ""

                apply_url = f"{self.BASE}{path}" if path.startswith("/") else path

                jobs.append(
                    JobOpportunity(
                        source=JobSource.WE_WORK_REMOTELY,
                        source_url=apply_url,
                        apply_url=apply_url,
                        title=title,
                        company=company,
                        location="Remote",
                        tech_stack=extract_tech_stack(title),
                        seniority=extract_seniority(title),
                    )
                )
            except Exception as e:
                logger.debug(f"WWR HTML parse error: {e}")

        return jobs

    @staticmethod
    def _strip_html(text: str) -> str:
        clean = re.compile(r"<[^>]+>")
        text = clean.sub(" ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Hacker News "Who is hiring?"
# ---------------------------------------------------------------------------


class HNHiringScraper:
    """
    Hacker News "Who is hiring?" scraper.

    Monthly threads with high-quality tech job postings.
    Uses Algolia HN Search API:
        https://hn.algolia.com/api/v1/search?query=who+is+hiring&tags=story
    """

    HN_API = "https://hacker-news.firebaseio.com/v0"
    ALGOLIA_API = "https://hn.algolia.com/api/v1"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def scrape(self, max_jobs: int = 200) -> list[JobOpportunity]:
        """
        Scrape latest "Who is hiring?" thread.

        Returns structured job opportunities from HN comments.
        """
        jobs: list[JobOpportunity] = []

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SpiderNix/0.2)"},
            follow_redirects=True,
        ) as client:
            # Step 1: Find the latest "Who is hiring?" thread
            search_url = f"{self.ALGOLIA_API}/search?query=who+is+hiring&tags=story&hitsPerPage=3"
            try:
                resp = await client.get(search_url)
                search_data = resp.json()
                hits = search_data.get("hits", [])

                # Find the most recent monthly thread
                thread_id = None
                for hit in hits:
                    title = hit.get("title", "")
                    if "who is hiring" in title.lower() and re.search(r"\b20\d{2}\b", title):
                        thread_id = hit.get("objectID")
                        break

                if not thread_id and hits:
                    thread_id = hits[0].get("objectID")

                if not thread_id:
                    logger.warning("No HN hiring thread found")
                    return jobs

                # Step 2: Get all comments (job postings)
                item_url = f"{self.HN_API}/item/{thread_id}.json"
                resp = await client.get(item_url)
                thread_data = resp.json()

                kids = thread_data.get("kids", [])
                comment_ids = kids[:max_jobs]

                # Fetch comments in batches
                for i in range(0, len(comment_ids), 20):
                    batch = comment_ids[i : i + 20]
                    tasks = [self._fetch_comment(client, cid) for cid in batch]
                    comments = await asyncio.gather(*tasks)

                    for comment in comments:
                        if comment is None:
                            continue
                        job = self._parse_hn_comment(comment)
                        if job:
                            jobs.append(job)

                    if len(jobs) >= max_jobs:
                        break

            except Exception as e:
                logger.error(f"HN scraper error: {e}")

        return jobs[:max_jobs]

    async def _fetch_comment(self, client: httpx.AsyncClient, comment_id: int) -> dict | None:
        """Fetch a single HN comment."""
        try:
            resp = await client.get(f"{self.HN_API}/item/{comment_id}.json")
            return resp.json()
        except Exception:
            return None

    def _parse_hn_comment(self, comment: dict) -> JobOpportunity | None:
        """Parse a HN comment into a job opportunity."""
        text = comment.get("text", "")
        if not text or len(text) < 50:
            return None

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)

        # Try to extract company name from first line
        lines = text.strip().split("\n")
        first_line = lines[0].strip() if lines else ""

        # Extract company from patterns like "CompanyName | Title | Location"
        company = ""
        title = ""
        location = ""

        pipe_parts = [p.strip() for p in first_line.split("|")]
        if len(pipe_parts) >= 2:
            company = pipe_parts[0]
            title = pipe_parts[1] if len(pipe_parts) > 1 else ""
            location = pipe_parts[2] if len(pipe_parts) > 2 else ""

        if not company:
            # Try "CompanyName - Title" or "CompanyName is hiring"
            for pattern in [
                r"^([A-Z][A-Za-z0-9\s\.]+?)\s+(is hiring|is looking)",
                r"^([A-Z][A-Za-z0-9\s\.]+?)\s+[-–—]",
            ]:
                m = re.match(pattern, first_line)
                if m:
                    company = m.group(1).strip()
                    break

        if not company:
            company = first_line[:60]

        # Extract apply URL
        apply_url = ""
        url_match = re.search(r'(https?://[^\s<>"]+)', text)
        if url_match:
            apply_url = url_match.group(1)

        # Tech stack
        tech_stack = extract_tech_stack(text)

        # Remote policy
        remote_policy = extract_remote_policy(text)

        # Salary
        salary = extract_salary(text)

        # Description is the full comment text
        description = text[:5000]

        return JobOpportunity(
            source=JobSource.HN_HIRING,
            source_url=f"https://news.ycombinator.com/item?id={comment.get('id', '')}",
            apply_url=apply_url,
            title=title or first_line[:100],
            company=company,
            location=location,
            description=description,
            remote_policy=remote_policy,
            tech_stack=tech_stack,
            seniority=extract_seniority(text),
            salary=salary,
            date_posted=datetime.fromtimestamp(comment.get("time", 0), tz=timezone.utc).isoformat()
            if comment.get("time")
            else None,
            raw_data=comment,
        )


# ---------------------------------------------------------------------------
# Convenience: scrape all boards
# ---------------------------------------------------------------------------


async def scrape_all_boards(
    skills: list[str] | None = None,
    search_terms: list[str] | None = None,
    max_per_source: int = 50,
    include_hn: bool = True,
    include_remoteok: bool = True,
    include_wwr: bool = True,
    timeout: float = 30.0,
) -> list[JobOpportunity]:
    """
    Scrape all configured job boards in parallel.

    Args:
        skills: Tech skills to search for (e.g. ['python', 'rust', 'nix'])
        search_terms: General search terms
        max_per_source: Max results per source
        include_hn: Include HN Who's Hiring
        include_remoteok: Include RemoteOK
        include_wwr: Include We Work Remotely

    Returns:
        Combined list of JobOpportunity objects
    """
    all_jobs: list[JobOpportunity] = []
    tasks = []

    remoteok = RemoteOKScraper(timeout=timeout) if include_remoteok else None
    wwr = WeWorkRemotelyScraper(timeout=timeout) if include_wwr else None
    hn = HNHiringScraper(timeout=timeout) if include_hn else None

    async def safe_scrape(name: str, coro) -> list[JobOpportunity]:
        try:
            return await coro
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            return []

    if remoteok and skills:
        tasks.append(safe_scrape("remoteok", remoteok.scrape(tags=skills, max_jobs=max_per_source)))
    elif remoteok and search_terms:
        for term in search_terms:
            tasks.append(
                safe_scrape(
                    "remoteok",
                    remoteok.scrape(search=term, max_jobs=max_per_source // len(search_terms)),
                )
            )
    elif remoteok:
        tasks.append(safe_scrape("remoteok", remoteok.scrape(max_jobs=max_per_source)))

    if wwr and search_terms:
        for term in search_terms:
            tasks.append(
                safe_scrape(
                    "wwr", wwr.scrape(search=term, max_jobs=max_per_source // len(search_terms))
                )
            )
    elif wwr:
        tasks.append(safe_scrape("wwr", wwr.scrape(max_jobs=max_per_source)))

    if hn:
        tasks.append(safe_scrape("hn", hn.scrape(max_jobs=max_per_source)))

    results = await asyncio.gather(*tasks)
    for jobs in results:
        all_jobs.extend(jobs)

    return all_jobs
