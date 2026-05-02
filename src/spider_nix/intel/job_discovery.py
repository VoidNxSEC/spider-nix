"""
Multi-source job discovery.

Sources (all public APIs, no auth required):
  - RemoteOK       https://remoteok.com/api
  - We Work Remotely  RSS feeds
  - Jobicy         https://jobicy.com/api/v2/remote-jobs
  - HN Who's Hiring   Algolia search on monthly threads
  - Company boards    Direct Greenhouse/Lever/Ashby polling

Flow:
  1. Fetch from all configured sources
  2. Deduplicate by URL
  3. Score against profile
  4. Filter already-seen URLs from tracker
  5. Save new candidates with status "queued"
  6. Return DiscoveryResult
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from .jobs import JobOpportunity
from .personal_scorer import score_opportunity
from .profile import Profile
from .tracker import Application, ApplicationTracker

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    new_jobs: int
    total_scanned: int
    sources_used: list[str]
    top_matches: list[tuple[JobOpportunity, float, list[str]]]
    # top_matches: (opportunity, score, reasons)
    timestamp: datetime = field(default_factory=datetime.now)


class JobDiscovery:
    """Discovers job opportunities from multiple public sources."""

    REMOTEOK_API = "https://remoteok.com/api"
    WWR_DEVOPS_RSS = "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
    WWR_BACKEND_RSS = "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
    JOBICY_API = "https://jobicy.com/api/v2/remote-jobs"
    HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"

    def __init__(self, profile: Profile, tracker: ApplicationTracker | None = None):
        self.profile = profile
        self.tracker = tracker or ApplicationTracker()

    async def run(self) -> DiscoveryResult:
        """
        Run full discovery cycle.

        Fetches from all configured sources in parallel,
        scores, deduplicates, and saves new jobs to tracker.
        """
        discovery_cfg = getattr(self.profile, "_discovery_cfg", {})
        sources = discovery_cfg.get("sources", ["remoteok", "weworkremotely", "jobicy"])
        min_score = discovery_cfg.get("min_score", 40.0)
        companies = discovery_cfg.get("companies", [])

        # Build tasks
        tasks = []
        used_sources = []

        if "remoteok" in sources:
            tasks.append(self._fetch_remoteok())
            used_sources.append("remoteok")

        if "weworkremotely" in sources:
            tasks.append(self._fetch_weworkremotely())
            used_sources.append("weworkremotely")

        if "jobicy" in sources:
            tasks.append(self._fetch_jobicy())
            used_sources.append("jobicy")

        if "hn_hiring" in sources:
            tasks.append(self._fetch_hn_hiring())
            used_sources.append("hn_hiring")

        if "companies" in sources and companies:
            tasks.append(self._fetch_company_boards(companies))
            used_sources.append("companies")

        # Fetch all sources in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate
        all_jobs: list[JobOpportunity] = []
        seen_urls: set[str] = set()

        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Source failed: {result}")
                continue
            for job in result:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

        total_scanned = len(all_jobs)

        # Get already-tracked URLs to avoid duplicates
        existing = await self.tracker.list_applications()
        existing_urls = {a["url"] for a in existing}

        # Score and filter
        new_jobs = []
        top_matches = []

        for job in all_jobs:
            if job.url in existing_urls:
                continue

            score, reasons = score_opportunity(job, self.profile)

            if score == 0.0:
                continue  # dealbreaker

            if score >= min_score:
                new_jobs.append((job, score, reasons))
                top_matches.append((job, score, reasons))

        # Sort by score descending
        new_jobs.sort(key=lambda x: x[1], reverse=True)
        top_matches = new_jobs[:10]

        # Save to tracker as "queued"
        saved = 0
        for job, score, reasons in new_jobs:
            app = Application(
                url=job.url,
                company=job.company,
                role=job.title or "Unknown Role",
                ats_platform="unknown",
                status="queued",
                notes=f"Score: {score:.0f} | {'; '.join(reasons[:3])}",
            )
            try:
                await self.tracker.record_application(app)
                saved += 1
            except Exception:
                pass  # already exists

        return DiscoveryResult(
            new_jobs=saved,
            total_scanned=total_scanned,
            sources_used=used_sources,
            top_matches=top_matches,
        )

    # ── Sources ────────────────────────────────────────────────────────────────

    async def _fetch_remoteok(self) -> list[JobOpportunity]:
        """Fetch from RemoteOK public API."""
        keywords = self._keywords_lower()

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    self.REMOTEOK_API,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for item in data:
                if not isinstance(item, dict) or "position" not in item:
                    continue

                title = item.get("position", "")
                tags = [t.lower() for t in item.get("tags", [])]
                description = item.get("description", "")
                content = f"{title} {' '.join(tags)} {description}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                salary = None
                s_min = item.get("salary_min")
                s_max = item.get("salary_max")
                if s_min or s_max:
                    salary = f"${s_min or '?'}–${s_max or '?'}"

                jobs.append(
                    JobOpportunity(
                        company=item.get("company", "Unknown"),
                        url=item.get("apply_url") or item.get("url", ""),
                        title=title,
                        remote_policy="Remote",
                        tech_stack=tags[:10],
                        salary_range=salary,
                    )
                )

            logger.info(f"RemoteOK: {len(jobs)} matching jobs")
            return jobs

        except Exception as e:
            logger.warning(f"RemoteOK fetch failed: {e}")
            return []

    async def _fetch_weworkremotely(self) -> list[JobOpportunity]:
        """Fetch from We Work Remotely RSS feeds."""
        keywords = self._keywords_lower()
        jobs = []

        for feed_url in [self.WWR_DEVOPS_RSS, self.WWR_BACKEND_RSS]:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(feed_url)
                    resp.raise_for_status()

                root = ET.fromstring(resp.text)
                channel = root.find("channel")
                if channel is None:
                    continue

                for item in channel.findall("item"):
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")

                    if title_el is None or link_el is None:
                        continue

                    title = title_el.text or ""
                    link = link_el.text or ""
                    desc = desc_el.text or "" if desc_el is not None else ""

                    # WWR title format: "Company: Role"
                    company = "Unknown"
                    role = title
                    if ":" in title:
                        parts = title.split(":", 1)
                        company = parts[0].strip()
                        role = parts[1].strip()

                    content = f"{title} {desc}".lower()
                    if not self._matches_keywords(content, keywords):
                        continue

                    jobs.append(
                        JobOpportunity(
                            company=company,
                            url=link,
                            title=role,
                            remote_policy="Remote",
                            tech_stack=[],
                        )
                    )

            except Exception as e:
                logger.warning(f"WWR fetch failed ({feed_url}): {e}")

        logger.info(f"WeWorkRemotely: {len(jobs)} matching jobs")
        return jobs

    async def _fetch_jobicy(self) -> list[JobOpportunity]:
        """Fetch from Jobicy public API."""
        keywords = self._keywords_lower()

        # Jobicy accepts one simple tag — use first single-word keyword
        single_word = next((k for k in keywords if " " not in k), keywords[0].split()[0])
        tag_param = single_word

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    self.JOBICY_API,
                    params={"count": 50, "tag": tag_param},
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for item in data.get("jobs", []):
                title = item.get("jobTitle", "")
                company = item.get("companyName", "Unknown")
                url = item.get("url", "")
                tags = [t.lower() for t in item.get("jobIndustry", [])]
                content = f"{title} {item.get('jobExcerpt', '')} {' '.join(tags)}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                salary = item.get("annualSalaryMin")
                salary_str = f"${salary}+" if salary else None

                jobs.append(
                    JobOpportunity(
                        company=company,
                        url=url,
                        title=title,
                        remote_policy="Remote",
                        tech_stack=tags,
                        salary_range=salary_str,
                    )
                )

            logger.info(f"Jobicy: {len(jobs)} matching jobs")
            return jobs

        except Exception as e:
            logger.warning(f"Jobicy fetch failed: {e}")
            return []

    async def _fetch_hn_hiring(self) -> list[JobOpportunity]:
        """
        Fetch from HN 'Who is Hiring?' monthly thread.

        Uses Algolia HN search API to find the latest thread
        and search comments for remote + keywords.
        """
        keywords = self._keywords_lower()

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Find the latest "Who is Hiring" thread
                search_resp = await client.get(
                    self.HN_ALGOLIA,
                    params={
                        "query": "Ask HN: Who is hiring?",
                        "tags": "story,ask_hn",
                        "hitsPerPage": 1,
                    },
                )
                search_resp.raise_for_status()
                hits = search_resp.json().get("hits", [])
                if not hits:
                    return []

                thread_id = hits[0]["objectID"]

                # Search comments in that thread
                query = " ".join(keywords[:3]) + " remote"
                comments_resp = await client.get(
                    self.HN_ALGOLIA,
                    params={
                        "query": query,
                        "tags": f"comment,story_{thread_id}",
                        "hitsPerPage": 30,
                    },
                )
                comments_resp.raise_for_status()
                comments = comments_resp.json().get("hits", [])

            jobs = []
            for comment in comments:
                text = comment.get("comment_text", "")
                if not text:
                    continue

                content = re.sub(r"<[^>]+>", " ", text).lower()

                if "remote" not in content:
                    continue

                if not self._matches_keywords(content, keywords):
                    continue

                # Extract company name (usually first line)
                lines = text.strip().split("\n")
                company_line = re.sub(r"<[^>]+>", "", lines[0]).strip()
                company = company_line[:50] if company_line else "HN Company"

                # HN comment URL
                hn_url = f"https://news.ycombinator.com/item?id={comment.get('objectID', '')}"

                jobs.append(
                    JobOpportunity(
                        company=company,
                        url=hn_url,
                        title="(see posting)",
                        remote_policy="Remote",
                        tech_stack=[],
                    )
                )

            logger.info(f"HN Hiring: {len(jobs)} matching comments")
            return jobs

        except Exception as e:
            logger.warning(f"HN hiring fetch failed: {e}")
            return []

    async def _fetch_company_boards(self, companies: list[dict]) -> list[JobOpportunity]:
        """
        Poll specific company ATS boards directly.

        Uses Greenhouse/Lever/Ashby public job listing APIs.
        These are polled regardless of keyword match — any open role
        at these companies is returned for scoring.
        """
        keywords = self._keywords_lower()
        tasks = []

        for company in companies:
            ats = company.get("ats", "greenhouse")
            slug = company.get("slug", "")
            name = company.get("name", slug)

            if ats == "greenhouse":
                tasks.append(self._fetch_greenhouse_board(name, slug, keywords))
            elif ats == "lever":
                tasks.append(self._fetch_lever_board(name, slug, keywords))
            elif ats == "ashby":
                tasks.append(self._fetch_ashby_board(name, slug, keywords))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        jobs = []
        for r in results:
            if isinstance(r, list):
                jobs.extend(r)

        logger.info(f"Company boards: {len(jobs)} matching jobs")
        return jobs

    async def _fetch_greenhouse_board(
        self, company: str, slug: str, keywords: list[str]
    ) -> list[JobOpportunity]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                    params={"content": "true"},
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for job in data.get("jobs", []):
                title = job.get("title", "")
                content = f"{title} {job.get('content', '')}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = job.get("absolute_url", "")
                jobs.append(
                    JobOpportunity(
                        company=company,
                        url=url,
                        title=title,
                        remote_policy=self._detect_remote_policy(content),
                        tech_stack=[],
                    )
                )

            return jobs
        except Exception:
            return []

    async def _fetch_lever_board(
        self, company: str, slug: str, keywords: list[str]
    ) -> list[JobOpportunity]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.lever.co/v0/postings/{slug}",
                    params={"mode": "json"},
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for posting in data:
                title = posting.get("text", "")
                desc = posting.get("descriptionPlain", "")
                content = f"{title} {desc}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = posting.get("hostedUrl", "")
                jobs.append(
                    JobOpportunity(
                        company=company,
                        url=url,
                        title=title,
                        remote_policy=self._detect_remote_policy(content),
                        tech_stack=[],
                    )
                )

            return jobs
        except Exception:
            return []

    async def _fetch_ashby_board(
        self, company: str, slug: str, keywords: list[str]
    ) -> list[JobOpportunity]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.ashbyhq.com/posting-api/job-board/{slug}/published"
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for posting in data.get("jobPostings", []):
                title = posting.get("title", "")
                desc = posting.get("descriptionPlain", "")
                content = f"{title} {desc}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = (
                    posting.get("externalLink", "")
                    or f"https://jobs.ashbyhq.com/{slug}/{posting.get('id', '')}"
                )

                jobs.append(
                    JobOpportunity(
                        company=company,
                        url=url,
                        title=title,
                        remote_policy=self._detect_remote_policy(content),
                        tech_stack=[],
                    )
                )

            return jobs
        except Exception:
            return []

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _keywords_lower(self) -> list[str]:
        """Get keywords from profile discovery config or fall back to target roles."""
        discovery_cfg = getattr(self.profile, "_discovery_cfg", {})
        keywords = discovery_cfg.get("keywords", [])
        if not keywords:
            keywords = [r.lower() for r in self.profile.preferences.target_roles]
        return [k.lower() for k in keywords]

    def _matches_keywords(self, content: str, keywords: list[str]) -> bool:
        """Return True if content matches ANY keyword."""
        return any(kw in content for kw in keywords)

    def _detect_remote_policy(self, content: str) -> str | None:
        if "remote" in content:
            return "Remote"
        if "hybrid" in content:
            return "Hybrid"
        if "on-site" in content or "onsite" in content:
            return "On-site"
        return None


def load_discovery_config(profile: Profile, raw_config: dict) -> None:
    """
    Attach discovery config dict to profile instance.

    Called from profile loader if [discovery] section exists.
    Stores as _discovery_cfg attribute (not a dataclass field
    to avoid breaking existing code).
    """
    object.__setattr__(profile, "_discovery_cfg", raw_config) if hasattr(
        profile, "__dataclass_fields__"
    ) else setattr(profile, "_discovery_cfg", raw_config)
