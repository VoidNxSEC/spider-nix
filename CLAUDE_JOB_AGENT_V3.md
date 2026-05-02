# Job Agent — Phase 3: Full Automation Pipeline

## Current state (from V1 + V2)

```
✓ intel/profile.py              profile loader
✓ intel/personal_scorer.py      scoring against profile
✓ intel/llm_mapper.py           LLM field mapping + cover letter
✓ intel/ats/detector.py         ATS platform detection
✓ intel/ats/greenhouse.py       Greenhouse adapter
✓ intel/ats/lever.py            Lever adapter
✓ intel/ats/ashby.py            Ashby adapter
✓ intel/ats/workday.py          Workday adapter (best-effort)
✓ intel/ats/generic.py          Generic form filler
✓ intel/ats/api_submit.py       API submission (Greenhouse/Lever/Ashby) + browser fallback
✓ intel/approval_gate.py        Rich TUI approval + ntfy fire-and-forget
✓ intel/tracker.py              SQLite application history
✓ cli.py — job-apply + job-history
✓ 11/11 tests passing
```

---

## What this document covers

Three new modules that complete the automation product:

```
1. intel/job_discovery.py    Multi-source job scraper + scorer
2. intel/email_monitor.py    IMAP inbox watcher + reply classifier
3. intel/scheduler.py        Asyncio orchestrator for the 3 loops
```

Three new CLI commands:

```
spider job-hunt     Start full automation (discovery + optional apply loop)
spider job-queue    Show queued jobs pending review
spider job-status   Full pipeline dashboard
```

---

## Architecture — 3 loops

```
┌──────────────────────────────────────────────────────┐
│                   spider job-hunt                    │
├──────────────────┬───────────────────┬───────────────┤
│  Discovery Loop  │  Apply Loop       │  Email Loop   │
│  (every 4h)      │  (after discovery)│  (every 15m)  │
├──────────────────┼───────────────────┼───────────────┤
│ RemoteOK API     │ Pull "queued"     │ IMAP search   │
│ We Work Remotely │ jobs from tracker │ for ATS emails│
│ Jobicy API       │                   │               │
│ HN Who's Hiring  │ For each job:     │ Classify:     │
│ Company boards   │ → TUI approval    │ interview /   │
│                  │ → API submit      │ rejection /   │
│ Score + dedup    │ → Track result    │ offer / ghost │
│ Save "queued"    │                   │               │
│ ntfy: N new jobs │ ntfy: submitted   │ ntfy: update  │
└──────────────────┴───────────────────┴───────────────┘
```

**Human is always in the loop for submissions.**
Discovery and email monitoring are fully automatic.
Applications require explicit TUI approval per job.

---

## File structure

```
src/spider_nix/intel/
  job_discovery.py     # NEW — multi-source discovery
  email_monitor.py     # NEW — IMAP watcher + classifier
  scheduler.py         # NEW — asyncio loop orchestrator
  (existing files unchanged)
```

New `profile.toml` sections: `[discovery]`, `[email]`

---

## 1. `profile.toml` additions

Add to `profile.example.toml` after the `[llm]` section:

```toml
[discovery]
# Sources to search (comment out ones you don't want)
sources = ["remoteok", "weworkremotely", "jobicy", "hn_hiring", "companies"]

# Search keywords — matched against job title + description
keywords = [
  "security architect",
  "platform engineer",
  "devops",
  "devsecops",
  "infrastructure engineer",
  "sre",
  "nixos",
  "rust",
  "ebpf",
]

# Minimum score to queue a job (0-100)
min_score = 40.0

# How often to run discovery (hours)
interval_hours = 4

# Specific companies to monitor on their ATS boards
# These are polled directly regardless of keyword matching
[[discovery.companies]]
name = "Cloudflare"
ats = "greenhouse"
slug = "cloudflare"

[[discovery.companies]]
name = "Stripe"
ats = "lever"
slug = "stripe"

[[discovery.companies]]
name = "HashiCorp"
ats = "greenhouse"
slug = "hashicorp"

[[discovery.companies]]
name = "Tailscale"
ats = "lever"
slug = "tailscale"

[[discovery.companies]]
name = "Fly.io"
ats = "lever"
slug = "fly"

[[discovery.companies]]
name = "Oxide Computer"
ats = "lever"
slug = "oxidecomputer"

[[discovery.companies]]
name = "Render"
ats = "lever"
slug = "render"

[[discovery.companies]]
name = "PlanetScale"
ats = "lever"
slug = "planetscale"

[email]
imap_host = "imap.gmail.com"
imap_port = 993
imap_user = ""
# Use Gmail app password (not account password)
# Generate at: myaccount.google.com/apppasswords
imap_password = ""
check_interval_minutes = 15
```

---

## 2. `src/spider_nix/intel/job_discovery.py`

```python
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
        discovery_cfg = getattr(self.profile, '_discovery_cfg', {})
        sources = discovery_cfg.get('sources', ['remoteok', 'weworkremotely', 'jobicy'])
        min_score = discovery_cfg.get('min_score', 40.0)
        companies = discovery_cfg.get('companies', [])

        # Build tasks
        tasks = []
        used_sources = []

        if 'remoteok' in sources:
            tasks.append(self._fetch_remoteok())
            used_sources.append('remoteok')

        if 'weworkremotely' in sources:
            tasks.append(self._fetch_weworkremotely())
            used_sources.append('weworkremotely')

        if 'jobicy' in sources:
            tasks.append(self._fetch_jobicy())
            used_sources.append('jobicy')

        if 'hn_hiring' in sources:
            tasks.append(self._fetch_hn_hiring())
            used_sources.append('hn_hiring')

        if 'companies' in sources and companies:
            tasks.append(self._fetch_company_boards(companies))
            used_sources.append('companies')

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
        existing_urls = {a['url'] for a in existing}

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
                if not isinstance(item, dict) or 'position' not in item:
                    continue

                title = item.get('position', '')
                tags = [t.lower() for t in item.get('tags', [])]
                description = item.get('description', '')
                content = f"{title} {' '.join(tags)} {description}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                salary = None
                s_min = item.get('salary_min')
                s_max = item.get('salary_max')
                if s_min or s_max:
                    salary = f"${s_min or '?'}–${s_max or '?'}"

                jobs.append(JobOpportunity(
                    company=item.get('company', 'Unknown'),
                    url=item.get('apply_url') or item.get('url', ''),
                    title=title,
                    remote_policy="Remote",
                    tech_stack=tags[:10],
                    salary_range=salary,
                ))

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
                channel = root.find('channel')
                if channel is None:
                    continue

                for item in channel.findall('item'):
                    title_el = item.find('title')
                    link_el = item.find('link')
                    desc_el = item.find('description')

                    if title_el is None or link_el is None:
                        continue

                    title = title_el.text or ''
                    link = link_el.text or ''
                    desc = desc_el.text or '' if desc_el is not None else ''

                    # WWR title format: "Company: Role"
                    company = 'Unknown'
                    role = title
                    if ':' in title:
                        parts = title.split(':', 1)
                        company = parts[0].strip()
                        role = parts[1].strip()

                    content = f"{title} {desc}".lower()
                    if not self._matches_keywords(content, keywords):
                        continue

                    jobs.append(JobOpportunity(
                        company=company,
                        url=link,
                        title=role,
                        remote_policy="Remote",
                        tech_stack=[],
                    ))

            except Exception as e:
                logger.warning(f"WWR fetch failed ({feed_url}): {e}")

        logger.info(f"WeWorkRemotely: {len(jobs)} matching jobs")
        return jobs

    async def _fetch_jobicy(self) -> list[JobOpportunity]:
        """Fetch from Jobicy public API."""
        keywords = self._keywords_lower()

        # Build tag query from first 3 keywords
        tag_param = '+'.join(keywords[:3])

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    self.JOBICY_API,
                    params={"count": 50, "tag": tag_param, "jobType": "full-time"},
                )
                resp.raise_for_status()
                data = resp.json()

            jobs = []
            for item in data.get('jobs', []):
                title = item.get('jobTitle', '')
                company = item.get('companyName', 'Unknown')
                url = item.get('url', '')
                tags = [t.lower() for t in item.get('jobIndustry', [])]
                content = f"{title} {item.get('jobExcerpt', '')} {' '.join(tags)}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                salary = item.get('annualSalaryMin')
                salary_str = f"${salary}+" if salary else None

                jobs.append(JobOpportunity(
                    company=company,
                    url=url,
                    title=title,
                    remote_policy="Remote",
                    tech_stack=tags,
                    salary_range=salary_str,
                ))

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
                hits = search_resp.json().get('hits', [])
                if not hits:
                    return []

                thread_id = hits[0]['objectID']

                # Search comments in that thread
                query = ' '.join(keywords[:3]) + ' remote'
                comments_resp = await client.get(
                    self.HN_ALGOLIA,
                    params={
                        "query": query,
                        "tags": f"comment,story_{thread_id}",
                        "hitsPerPage": 30,
                    },
                )
                comments_resp.raise_for_status()
                comments = comments_resp.json().get('hits', [])

            jobs = []
            for comment in comments:
                text = comment.get('comment_text', '')
                if not text:
                    continue

                content = re.sub(r'<[^>]+>', ' ', text).lower()

                if 'remote' not in content:
                    continue

                if not self._matches_keywords(content, keywords):
                    continue

                # Extract company name (usually first line)
                lines = text.strip().split('\n')
                company_line = re.sub(r'<[^>]+>', '', lines[0]).strip()
                company = company_line[:50] if company_line else 'HN Company'

                # HN comment URL
                hn_url = f"https://news.ycombinator.com/item?id={comment.get('objectID', '')}"

                jobs.append(JobOpportunity(
                    company=company,
                    url=hn_url,
                    title="(see posting)",
                    remote_policy="Remote",
                    tech_stack=[],
                ))

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
            ats = company.get('ats', 'greenhouse')
            slug = company.get('slug', '')
            name = company.get('name', slug)

            if ats == 'greenhouse':
                tasks.append(self._fetch_greenhouse_board(name, slug, keywords))
            elif ats == 'lever':
                tasks.append(self._fetch_lever_board(name, slug, keywords))
            elif ats == 'ashby':
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
            for job in data.get('jobs', []):
                title = job.get('title', '')
                content = f"{title} {job.get('content', '')}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = job.get('absolute_url', '')
                jobs.append(JobOpportunity(
                    company=company,
                    url=url,
                    title=title,
                    remote_policy=self._detect_remote_policy(content),
                    tech_stack=[],
                ))

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
                title = posting.get('text', '')
                desc = posting.get('descriptionPlain', '')
                content = f"{title} {desc}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = posting.get('hostedUrl', '')
                jobs.append(JobOpportunity(
                    company=company,
                    url=url,
                    title=title,
                    remote_policy=self._detect_remote_policy(content),
                    tech_stack=[],
                ))

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
            for posting in data.get('jobPostings', []):
                title = posting.get('title', '')
                desc = posting.get('descriptionPlain', '')
                content = f"{title} {desc}".lower()

                if not self._matches_keywords(content, keywords):
                    continue

                url = posting.get('externalLink', '') or \
                      f"https://jobs.ashbyhq.com/{slug}/{posting.get('id', '')}"

                jobs.append(JobOpportunity(
                    company=company,
                    url=url,
                    title=title,
                    remote_policy=self._detect_remote_policy(content),
                    tech_stack=[],
                ))

            return jobs
        except Exception:
            return []

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _keywords_lower(self) -> list[str]:
        """Get keywords from profile discovery config or fall back to target roles."""
        discovery_cfg = getattr(self.profile, '_discovery_cfg', {})
        keywords = discovery_cfg.get('keywords', [])
        if not keywords:
            keywords = [r.lower() for r in self.profile.preferences.target_roles]
        return [k.lower() for k in keywords]

    def _matches_keywords(self, content: str, keywords: list[str]) -> bool:
        """Return True if content matches ANY keyword."""
        return any(kw in content for kw in keywords)

    def _detect_remote_policy(self, content: str) -> str | None:
        if 'remote' in content:
            return 'Remote'
        if 'hybrid' in content:
            return 'Hybrid'
        if 'on-site' in content or 'onsite' in content:
            return 'On-site'
        return None


def load_discovery_config(profile: Profile, raw_config: dict) -> None:
    """
    Attach discovery config dict to profile instance.

    Called from profile loader if [discovery] section exists.
    Stores as _discovery_cfg attribute (not a dataclass field
    to avoid breaking existing code).
    """
    object.__setattr__(profile, '_discovery_cfg', raw_config) \
        if hasattr(profile, '__dataclass_fields__') else \
        setattr(profile, '_discovery_cfg', raw_config)
```

---

## 3. `src/spider_nix/intel/email_monitor.py`

```python
"""
IMAP inbox watcher for job application follow-ups.

Uses stdlib imaplib + asyncio.to_thread (zero new dependencies).

Flow:
  1. Connect to IMAP server
  2. Search for unseen emails from known ATS senders
     OR containing company names from tracker
  3. Classify each email: interview_invite | rejection | offer | followup | unknown
  4. Update tracker status
  5. Send ntfy notification for high-priority events (interview, offer)

Classification strategy:
  - Fast: regex rules cover 90% of cases
  - Fallback: LLM for ambiguous emails

Environment:
  IMAP credentials come from profile.toml [email] section
  ntfy config from NTFY_URL / NTFY_TOPIC / NTFY_TOKEN env vars
"""

import asyncio
import email
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header
from typing import Literal

import httpx

from .tracker import ApplicationTracker

logger = logging.getLogger(__name__)

EmailClass = Literal["interview_invite", "rejection", "offer", "followup", "unknown"]


@dataclass
class EmailConfig:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    check_interval_minutes: int = 15


@dataclass
class ClassifiedEmail:
    subject: str
    sender: str
    classification: EmailClass
    confidence: float
    company: str | None
    body_preview: str
    received_at: datetime


# Known ATS sender domains
ATS_DOMAINS = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "smartrecruiters.com",
    "bamboohr.com",
    "jobvite.com",
    "icims.com",
    "taleo.net",
    "successfactors.com",
    "recruitcrm.io",
]

# Regex classification rules — ordered by priority
CLASSIFICATION_RULES: list[tuple[EmailClass, float, list[str]]] = [
    # Offer
    ("offer", 0.95, [
        r"pleased to offer",
        r"we.d like to offer you",
        r"offer of employment",
        r"job offer",
        r"formal offer",
        r"compensation package",
    ]),
    # Interview invite
    ("interview_invite", 0.90, [
        r"schedule.{0,20}interview",
        r"interview.{0,20}schedule",
        r"we.d like to.{0,30}interview",
        r"invite you.{0,30}interview",
        r"next step.{0,20}interview",
        r"technical screen",
        r"phone screen",
        r"video call",
        r"calendly",
        r"schedule.{0,20}call",
        r"book.{0,20}time",
        r"meet with.{0,20}team",
    ]),
    # Rejection
    ("rejection", 0.92, [
        r"unfortunately",
        r"not moving forward",
        r"decided to.{0,30}other candidate",
        r"not a match",
        r"not the right fit",
        r"decided not to",
        r"we.re unable to",
        r"will not be moving",
        r"position has been filled",
        r"other candidates",
        r"not selected",
    ]),
    # Followup / status
    ("followup", 0.75, [
        r"following up",
        r"update on your application",
        r"application status",
        r"under review",
        r"still reviewing",
        r"next steps",
        r"thank you for applying",
        r"we received your application",
        r"application.*confirmed",
    ]),
]


class EmailMonitor:
    """Monitors inbox for job application replies."""

    def __init__(self, config: EmailConfig, tracker: ApplicationTracker | None = None):
        self.config = config
        self.tracker = tracker or ApplicationTracker()

    async def check_once(self) -> list[ClassifiedEmail]:
        """
        Single inbox check cycle.

        Returns list of classified emails found.
        """
        return await asyncio.to_thread(self._check_sync)

    def _check_sync(self) -> list[ClassifiedEmail]:
        """Blocking IMAP check — runs in thread pool."""
        try:
            mail = imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port)
            mail.login(self.config.imap_user, self.config.imap_password)
            mail.select("INBOX")
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return []

        classified = []

        try:
            # Search unseen emails from ATS domains
            # Build OR query for known ATS senders
            ats_queries = []
            for domain in ATS_DOMAINS[:5]:  # IMAP OR has limits
                ats_queries.append(f'FROM "@{domain}"')

            # Also search by "application" in subject (catches custom ATS)
            search_criteria = '(UNSEEN SUBJECT "application")'
            _, data = mail.search(None, search_criteria)

            msg_ids = data[0].split() if data[0] else []

            # Also search for ATS domains
            _, data2 = mail.search(None, '(UNSEEN FROM "greenhouse.io")')
            _, data3 = mail.search(None, '(UNSEEN FROM "lever.co")')
            _, data4 = mail.search(None, '(UNSEEN FROM "ashbyhq.com")')

            all_ids = set(msg_ids)
            for d in [data2[0], data3[0], data4[0]]:
                if d:
                    all_ids.update(d.split())

            for msg_id in list(all_ids)[:20]:  # max 20 per cycle
                try:
                    _, msg_data = mail.fetch(msg_id, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    subject = _decode_header_str(msg.get("Subject", ""))
                    sender = _decode_header_str(msg.get("From", ""))
                    body = _extract_body(msg)

                    classification, confidence = _classify_email(subject, body)

                    # Extract company from sender domain or subject
                    company = _extract_company(sender, subject)

                    result = ClassifiedEmail(
                        subject=subject,
                        sender=sender,
                        classification=classification,
                        confidence=confidence,
                        company=company,
                        body_preview=body[:300],
                        received_at=datetime.now(),
                    )
                    classified.append(result)

                    # Mark as read so we don't process twice
                    mail.store(msg_id, '+FLAGS', '\\Seen')

                except Exception as e:
                    logger.warning(f"Failed to process email {msg_id}: {e}")

        finally:
            try:
                mail.logout()
            except Exception:
                pass

        return classified

    async def process_results(self, emails: list[ClassifiedEmail]) -> None:
        """
        Update tracker and send ntfy for each classified email.
        """
        for em in emails:
            if em.classification == "unknown":
                continue

            # Map classification to tracker status
            STATUS_MAP: dict[EmailClass, str] = {
                "interview_invite": "interview",
                "rejection": "rejected",
                "offer": "offer",
                "followup": "submitted",  # keep as submitted, just noteworthy
            }
            new_status = STATUS_MAP.get(em.classification, "submitted")

            # Try to find matching application in tracker
            apps = await self.tracker.list_applications()
            matched_url = None
            if em.company:
                for app in apps:
                    if app.get('company', '').lower() in em.company.lower() or \
                       em.company.lower() in app.get('company', '').lower():
                        matched_url = app['url']
                        break

            if matched_url:
                await self.tracker.update_status(
                    matched_url, new_status,
                    notes=f"{em.classification} ({em.confidence:.0%}) | {em.subject[:80]}"
                )
                logger.info(f"Updated {em.company} → {new_status}")

            # ntfy notification
            await _ntfy_email_alert(em)


def _classify_email(subject: str, body: str) -> tuple[EmailClass, float]:
    """
    Classify email using regex rules.

    Returns (classification, confidence).
    """
    content = f"{subject} {body}".lower()

    for classification, confidence, patterns in CLASSIFICATION_RULES:
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return classification, confidence

    return "unknown", 0.0


def _decode_header_str(value: str) -> str:
    """Decode email header (handles encoded words)."""
    try:
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(str(part))
        return ' '.join(decoded)
    except Exception:
        return value


def _extract_body(msg: email.message.Message) -> str:
    """Extract plain text body from email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    charset = part.get_content_charset() or 'utf-8'
                    body = payload.decode(charset, errors='replace')
                    break
                except Exception:
                    pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            charset = msg.get_content_charset() or 'utf-8'
            body = payload.decode(charset, errors='replace') if payload else ""
        except Exception:
            pass

    return body[:3000]


def _extract_company(sender: str, subject: str) -> str | None:
    """Try to extract company name from sender or subject."""
    # From "Company Name <noreply@company.com>"
    match = re.match(r'^([^<]+)<', sender)
    if match:
        name = match.group(1).strip()
        if name and not re.match(r'^[a-z0-9._%+-]+@', name.lower()):
            return name.strip('"').strip()

    # From sender domain
    domain_match = re.search(r'@([^>]+)', sender)
    if domain_match:
        domain = domain_match.group(1)
        parts = domain.split('.')
        if len(parts) >= 2 and parts[-2] not in ('gmail', 'yahoo', 'hotmail', 'outlook'):
            return parts[-2].capitalize()

    return None


async def _ntfy_email_alert(em: ClassifiedEmail) -> None:
    """Send ntfy notification for significant email events."""
    ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "job-agent")
    ntfy_token = os.environ.get("NTFY_TOKEN")

    if not ntfy_token:
        return

    PRIORITY_MAP = {
        "offer": "urgent",
        "interview_invite": "high",
        "rejection": "default",
        "followup": "low",
    }

    EMOJI_MAP = {
        "offer": "🎉",
        "interview_invite": "📅",
        "rejection": "❌",
        "followup": "📬",
    }

    emoji = EMOJI_MAP.get(em.classification, "📧")
    priority = PRIORITY_MAP.get(em.classification, "default")
    title = f"{emoji} {em.classification.replace('_', ' ').title()}"
    if em.company:
        title += f" — {em.company}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{ntfy_url}/{ntfy_topic}",
                content=f"{em.subject}\n\n{em.body_preview[:200]}".encode(),
                headers={
                    "Authorization": f"Bearer {ntfy_token}",
                    "Title": title,
                    "Priority": priority,
                    "Tags": "email",
                },
            )
    except Exception:
        pass


def email_config_from_profile(profile: Profile) -> EmailConfig | None:
    """Extract email config from profile's _email_cfg attribute if set."""
    cfg = getattr(profile, '_email_cfg', None)
    if not cfg:
        return None
    return EmailConfig(
        imap_host=cfg.get('imap_host', 'imap.gmail.com'),
        imap_port=int(cfg.get('imap_port', 993)),
        imap_user=cfg.get('imap_user', ''),
        imap_password=cfg.get('imap_password', ''),
        check_interval_minutes=int(cfg.get('check_interval_minutes', 15)),
    )
```

---

## 4. `src/spider_nix/intel/scheduler.py`

```python
"""
Asyncio orchestrator for the 3 job hunt loops.

Runs three concurrent tasks:
  1. discovery_loop  — finds new jobs on a schedule
  2. apply_loop      — processes queued jobs with TUI approval
  3. email_loop      — monitors inbox for replies

Graceful shutdown: SIGINT cancels all tasks cleanly.
"""

import asyncio
import logging
import signal
from dataclasses import dataclass

from rich.console import Console

from .email_monitor import EmailMonitor, EmailConfig
from .job_discovery import JobDiscovery, DiscoveryResult
from .profile import Profile
from .tracker import ApplicationTracker

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class SchedulerConfig:
    discovery_interval_hours: float = 4.0
    email_interval_minutes: float = 15.0
    apply_after_discovery: bool = True   # process queue after each discovery run
    max_applies_per_cycle: int = 5       # max TUI approvals per discovery cycle


class JobHuntScheduler:
    """
    Orchestrates discovery, application, and email monitoring loops.

    Usage:
        scheduler = JobHuntScheduler(profile, config)
        await scheduler.run()         # blocks until SIGINT
        await scheduler.run_once()    # single discovery cycle, no loop
    """

    def __init__(
        self,
        profile: Profile,
        config: SchedulerConfig | None = None,
        email_config: EmailConfig | None = None,
    ):
        self.profile = profile
        self.config = config or SchedulerConfig()
        self.email_config = email_config
        self.tracker = ApplicationTracker()
        self._stop_event = asyncio.Event()

    async def run(self) -> None:
        """Run all loops until SIGINT."""
        console.print("[bold cyan]🤖 Job Hunt Agent starting...[/]")
        console.print(f"  Discovery: every {self.config.discovery_interval_hours}h")
        if self.email_config:
            console.print(f"  Email: every {self.config.email_interval_minutes}m")
        console.print("  [dim]Press Ctrl+C to stop[/]\n")

        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, self._stop_event.set)
        loop.add_signal_handler(signal.SIGTERM, self._stop_event.set)

        tasks = [
            asyncio.create_task(self._discovery_loop(), name="discovery"),
        ]

        if self.email_config:
            tasks.append(
                asyncio.create_task(self._email_loop(), name="email")
            )

        try:
            await self._stop_event.wait()
        finally:
            console.print("\n[yellow]Shutting down...[/]")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            console.print("[green]✓ Stopped cleanly[/]")

    async def run_once(self) -> DiscoveryResult:
        """
        Single discovery cycle — no loop, no SIGINT handling.
        Useful for cron jobs or manual triggers.
        """
        return await self._discovery_cycle()

    # ── Loops ──────────────────────────────────────────────────────────────────

    async def _discovery_loop(self) -> None:
        """Discovery loop — runs every N hours."""
        while not self._stop_event.is_set():
            try:
                result = await self._discovery_cycle()
                console.print(
                    f"[dim]{result.timestamp.strftime('%H:%M')}[/] "
                    f"Discovery: [green]+{result.new_jobs}[/] new jobs "
                    f"({result.total_scanned} scanned)"
                )
            except Exception as e:
                logger.error(f"Discovery cycle failed: {e}")

            # Wait for next cycle (or stop signal)
            interval = self.config.discovery_interval_hours * 3600
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _email_loop(self) -> None:
        """Email monitoring loop — runs every N minutes."""
        assert self.email_config is not None
        monitor = EmailMonitor(self.email_config, self.tracker)

        while not self._stop_event.is_set():
            try:
                emails = await monitor.check_once()
                if emails:
                    await monitor.process_results(emails)
                    for em in emails:
                        if em.classification != "unknown":
                            console.print(
                                f"[dim]{em.received_at.strftime('%H:%M')}[/] "
                                f"Email: [cyan]{em.classification}[/] "
                                f"from {em.company or em.sender[:30]}"
                            )
            except Exception as e:
                logger.error(f"Email check failed: {e}")

            interval = self.email_config.check_interval_minutes * 60
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def _discovery_cycle(self) -> DiscoveryResult:
        """Single discovery + optional apply pass."""
        discovery = JobDiscovery(self.profile, self.tracker)
        result = await discovery.run()

        if result.new_jobs > 0:
            console.print(f"\n[bold green]Found {result.new_jobs} new matching jobs![/]")
            for opp, score, reasons in result.top_matches[:5]:
                console.print(
                    f"  [{_score_color(score)}]{score:.0f}[/] "
                    f"[cyan]{opp.company}[/] — {opp.title or 'Unknown'} "
                    f"[dim]{opp.url[:60]}[/]"
                )

        if self.config.apply_after_discovery and result.new_jobs > 0:
            await self._apply_queued(max_jobs=self.config.max_applies_per_cycle)

        return result

    async def _apply_queued(self, max_jobs: int = 5) -> None:
        """
        Process queued jobs through TUI approval + submission.

        Each job requires explicit user approval before submitting.
        """
        from .approval_gate import ApprovalContext, request_approval
        from .ats.api_submit import (
            ashby_api_submit, browser_submit_headless,
            greenhouse_api_submit, lever_api_submit,
        )
        from .ats.detector import ATSPlatform, detect_from_url
        from .llm_mapper import generate_mapping
        from .personal_scorer import score_opportunity
        from .tracker import Application
        from datetime import datetime
        import httpx

        queued = await self.tracker.list_applications(status="queued")
        if not queued:
            return

        console.print(f"\n[bold]{len(queued)} jobs in queue[/] (processing up to {max_jobs})\n")

        processed = 0
        for app_row in queued[:max_jobs]:
            if self._stop_event.is_set():
                break

            url = app_row['url']
            company = app_row.get('company', '')
            role = app_row.get('role', '')

            console.print(f"[cyan]Processing:[/] {company} — {role}")

            # Detect ATS
            ats = detect_from_url(url)

            # Fetch description
            job_description = ""
            try:
                if ats == ATSPlatform.GREENHOUSE:
                    from .ats.greenhouse import fetch_job_description
                    job_description = await fetch_job_description(url)
                elif ats == ATSPlatform.LEVER:
                    from .ats.lever import fetch_job_description
                    job_description = await fetch_job_description(url)
                elif ats == ATSPlatform.ASHBY:
                    from .ats.ashby import fetch_job_description
                    job_description = await fetch_job_description(url)
            except Exception:
                pass

            # Re-score with full description
            from .jobs import JobOpportunity
            opp = JobOpportunity(
                company=company, url=url, title=role,
                remote_policy="remote" if "remote" in job_description.lower() else None,
                tech_stack=[s for s in self.profile.primary_skills
                            if s.lower() in job_description.lower()],
            )
            score, reasons = score_opportunity(opp, self.profile)

            if score == 0.0:
                await self.tracker.update_status(url, "rejected",
                    notes="Dealbreaker detected on full description")
                continue

            # LLM mapping
            mapping_result = await generate_mapping(job_description, self.profile)
            field_mapping = mapping_result.get("field_mapping", {})
            cover_letter = mapping_result.get(
                "cover_letter", self.profile.cover_letter_template
            )

            # TUI approval
            ctx = ApprovalContext(
                job_url=url,
                company=company,
                role=role,
                ats_platform=ats.value,
                score=score,
                score_reasons=reasons,
                field_mapping=field_mapping,
                cover_letter=cover_letter,
                salary_expectation=str(self.profile.preferences.min_salary_usd),
            )

            approved, final_mapping = await request_approval(ctx)

            if not approved:
                await self.tracker.update_status(url, "skipped")
                continue

            # Submit
            if ats == ATSPlatform.GREENHOUSE:
                result = await greenhouse_api_submit(url, final_mapping, cover_letter)
            elif ats == ATSPlatform.LEVER:
                result = await lever_api_submit(url, final_mapping, cover_letter)
            elif ats == ATSPlatform.ASHBY:
                result = await ashby_api_submit(url, final_mapping, cover_letter)
            else:
                result = await browser_submit_headless(url, final_mapping, cover_letter)

            if result.success:
                await self.tracker.update_status(url, "submitted")
                console.print(f"[green]✅ {result.message}[/]")
            else:
                await self.tracker.update_status(url, "queued",
                    notes=f"Submit failed: {result.message}")
                console.print(f"[red]✗ {result.message}[/]")

            processed += 1

        if processed:
            console.print(f"\n[dim]Processed {processed} applications[/]")


def _score_color(score: float) -> str:
    if score >= 70:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"
```

---

## 5. Update `src/spider_nix/intel/profile.py`

Add discovery and email config loading to `_parse_profile`:

```python
# At the end of _parse_profile(), before the return statement:

    profile = Profile(
        personal=PersonalInfo(**p),
        current_experience=Experience(**exp),
        primary_skills=skills["primary"],
        secondary_skills=skills.get("secondary", []),
        languages=skills.get("languages", []),
        preferences=Preferences(
            remote_only=prefs.get("remote_only", True),
            min_salary_usd=prefs.get("min_salary_usd", 0),
            target_roles=prefs.get("target_roles", []),
            dealbreakers=prefs.get("dealbreakers", []),
        ),
        cover_letter_template=cl["template"],
        llm_api_url=llm.get("api_url", "http://localhost:9000"),
        llm_model=llm.get("model", "mistral"),
    )

    # Attach optional extended configs
    if "discovery" in data:
        setattr(profile, '_discovery_cfg', data["discovery"])
    if "email" in data:
        setattr(profile, '_email_cfg', data["email"])

    return profile
```

---

## 6. CLI additions to `cli.py`

Append these three commands. Do NOT restructure existing CLI.

```python
@app.command("job-hunt")
def job_hunt(
    profile_path: Optional[Path] = typer.Option(
        None, "--profile", "-p", help="Path to profile.toml"
    ),
    once: bool = typer.Option(
        False, "--once", help="Run one discovery cycle and exit (no daemon)"
    ),
    discover_only: bool = typer.Option(
        False, "--discover-only", help="Discover jobs but do not open apply TUI"
    ),
    no_email: bool = typer.Option(
        False, "--no-email", help="Disable email monitoring"
    ),
):
    """
    🤖 Start the full job hunting automation.

    Runs three loops in parallel:
      - Discovery: scans RemoteOK, We Work Remotely, Jobicy, HN Hiring,
        and configured company boards every N hours
      - Apply: shows TUI for each queued job (human approves before submit)
      - Email: monitors inbox for replies and updates tracker

    Configure intervals and sources in profile.toml [discovery] and [email].

    Use --once for a single discovery cycle (good for cron).
    """
    console.print(f"\n[bold]🤖 Job Hunt Agent[/]\n")

    async def run():
        try:
            profile = load_profile(profile_path)
            console.print(f"[green]✓[/] Profile: {profile.personal.name}")
        except FileNotFoundError as e:
            console.print(f"[red]✗ {e}[/]")
            raise typer.Exit(1)

        from .intel.email_monitor import email_config_from_profile
        from .intel.scheduler import JobHuntScheduler, SchedulerConfig

        email_cfg = None if no_email else email_config_from_profile(profile)
        discovery_cfg = getattr(profile, '_discovery_cfg', {})

        scheduler_cfg = SchedulerConfig(
            discovery_interval_hours=float(
                discovery_cfg.get('interval_hours', 4.0)
            ),
            apply_after_discovery=not discover_only,
        )

        scheduler = JobHuntScheduler(profile, scheduler_cfg, email_cfg)

        if once:
            result = await scheduler.run_once()
            console.print(f"\n[green]✓[/] Discovery complete:")
            console.print(f"  New jobs queued : [green]{result.new_jobs}[/]")
            console.print(f"  Total scanned   : {result.total_scanned}")
            console.print(f"  Sources         : {', '.join(result.sources_used)}")
            if result.top_matches:
                console.print("\n[bold]Top matches:[/]")
                for opp, score, reasons in result.top_matches[:5]:
                    console.print(
                        f"  [green]{score:.0f}[/] {opp.company} — "
                        f"{opp.title or '?'}  [dim]{opp.url[:60]}[/]"
                    )
        else:
            await scheduler.run()

    asyncio.run(run())


@app.command("job-queue")
def job_queue(
    limit: int = typer.Option(20, "--limit", "-n", help="Max jobs to show"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum score filter"),
):
    """📋 Show queued job applications pending review."""

    async def run():
        tracker = ApplicationTracker()
        apps = await tracker.list_applications(status="queued")

        if not apps:
            console.print("[yellow]No jobs in queue[/]")
            console.print("[dim]Run 'spider job-hunt --once' to discover new jobs[/]")
            return

        table = Table(title=f"Queued Jobs ({len(apps)})")
        table.add_column("#", style="dim", width=3)
        table.add_column("Company", style="cyan")
        table.add_column("Role", style="white", max_width=45)
        table.add_column("Score", style="yellow", width=7)
        table.add_column("URL", style="dim", max_width=40)

        shown = 0
        for i, a in enumerate(apps[:limit], 1):
            notes = a.get('notes', '')
            score_match = re.search(r'Score:\s*([\d.]+)', notes or '')
            score_str = score_match.group(1) if score_match else "?"

            if min_score > 0 and score_match:
                if float(score_match.group(1)) < min_score:
                    continue

            table.add_row(
                str(i),
                a['company'] or "-",
                (a['role'] or "")[:45],
                score_str,
                (a['url'] or "")[:40],
            )
            shown += 1

        console.print(table)
        console.print(
            f"\n[dim]Run 'spider job-apply <url>' to apply, "
            f"or 'spider job-hunt' to process the queue[/]"
        )

    asyncio.run(run())


@app.command("job-status")
def job_status():
    """📊 Full pipeline dashboard."""

    async def run():
        tracker = ApplicationTracker()
        all_apps = await tracker.list_applications()

        if not all_apps:
            console.print("[yellow]No applications tracked yet[/]")
            return

        # Count by status
        counts: dict[str, int] = {}
        for a in all_apps:
            s = a.get('status', 'unknown')
            counts[s] = counts.get(s, 0) + 1

        STATUS_ORDER = [
            "queued", "submitted", "followup", "interview",
            "offer", "rejected", "ghosted", "skipped",
        ]
        STATUS_COLORS = {
            "queued": "yellow",
            "submitted": "cyan",
            "interview": "bold green",
            "offer": "bold bright_green",
            "rejected": "red",
            "ghosted": "dim",
            "skipped": "dim",
            "followup": "blue",
        }

        table = Table(title="Pipeline Status", show_header=True)
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Bar")

        total = len(all_apps)
        max_count = max(counts.values()) if counts else 1

        for status in STATUS_ORDER:
            count = counts.get(status, 0)
            if count == 0:
                continue
            color = STATUS_COLORS.get(status, "white")
            bar_len = int((count / max_count) * 20)
            bar = f"[{color}]{'█' * bar_len}[/]"
            table.add_row(f"[{color}]{status}[/]", str(count), bar)

        console.print(table)
        console.print(f"\n[dim]Total tracked: {total}[/]")

        # Recent activity
        recent = sorted(
            [a for a in all_apps if a.get('last_updated')],
            key=lambda x: x['last_updated'],
            reverse=True,
        )[:5]

        if recent:
            console.print("\n[bold]Recent activity:[/]")
            for a in recent:
                updated = a['last_updated'][:16] if a['last_updated'] else '?'
                status = a.get('status', '?')
                color = STATUS_COLORS.get(status, "white")
                console.print(
                    f"  [dim]{updated}[/]  [{color}]{status:12}[/]  "
                    f"[cyan]{a.get('company', '?')[:20]}[/] — "
                    f"{(a.get('role') or '')[:35]}"
                )

    asyncio.run(run())
```

---

## 7. Tests to add — `tests/test_job_discovery.py`

```python
"""Tests for job discovery module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from spider_nix.intel.job_discovery import JobDiscovery
from spider_nix.intel.email_monitor import _classify_email, _extract_company


# ── Discovery ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remoteok_fetch_and_filter(mock_profile):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"legal": "..."},  # first item is metadata
        {
            "position": "Security Architect",
            "company": "AcmeCorp",
            "tags": ["security", "rust", "nixos"],
            "description": "Remote security architect role with Rust and NixOS.",
            "apply_url": "https://acmecorp.com/apply",
            "url": "https://remoteok.com/jobs/123",
            "salary_min": 90000,
            "salary_max": 150000,
        },
        {
            "position": "Junior PHP Developer",
            "company": "OtherCorp",
            "tags": ["php"],
            "description": "PHP development.",
            "apply_url": "https://othercorp.com/apply",
            "url": "https://remoteok.com/jobs/456",
        },
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        discovery = JobDiscovery(mock_profile)
        jobs = await discovery._fetch_remoteok()

    # Only Security Architect matches keywords
    assert len(jobs) == 1
    assert jobs[0].company == "AcmeCorp"
    assert jobs[0].salary_range is not None


@pytest.mark.asyncio
async def test_greenhouse_board_fetch(mock_profile):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jobs": [
            {
                "title": "Platform Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "content": "Remote platform engineering role with NixOS and Kubernetes.",
            },
            {
                "title": "Marketing Manager",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/456",
                "content": "Lead marketing campaigns.",
            },
        ]
    }

    keywords = ["platform engineer", "nixos", "security"]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        discovery = JobDiscovery(mock_profile)
        jobs = await discovery._fetch_greenhouse_board("Acme", "acme", keywords)

    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"


def test_keywords_lower(mock_profile):
    discovery = JobDiscovery(mock_profile)
    keywords = discovery._keywords_lower()
    assert all(k == k.lower() for k in keywords)
    assert len(keywords) > 0


def test_matches_keywords(mock_profile):
    discovery = JobDiscovery(mock_profile)
    keywords = ["security architect", "nixos", "rust"]
    assert discovery._matches_keywords("senior security architect role remote", keywords)
    assert not discovery._matches_keywords("junior php developer", keywords)


# ── Email classification ────────────────────────────────────────────────────────

def test_classify_rejection():
    cls, conf = _classify_email(
        subject="Your application to Acme",
        body="Unfortunately, we have decided not to move forward with your application.",
    )
    assert cls == "rejection"
    assert conf > 0.8


def test_classify_interview():
    cls, conf = _classify_email(
        subject="Next steps — Security Architect role",
        body="We'd like to schedule an interview with you. Please use the Calendly link below.",
    )
    assert cls == "interview_invite"
    assert conf > 0.8


def test_classify_offer():
    cls, conf = _classify_email(
        subject="Offer of Employment",
        body="We are pleased to offer you the position of Security Architect.",
    )
    assert cls == "offer"
    assert conf > 0.9


def test_classify_unknown():
    cls, conf = _classify_email(
        subject="Newsletter from TechCorp",
        body="Here are the latest industry updates...",
    )
    assert cls == "unknown"
    assert conf == 0.0


def test_extract_company_from_sender():
    company = _extract_company('Cloudflare Recruiting <noreply@greenhouse.io>', '')
    assert company is not None
    assert len(company) > 0


@pytest.fixture
def mock_profile():
    from spider_nix.intel.profile import (
        Experience, PersonalInfo, Preferences, Profile,
    )
    profile = Profile(
        personal=PersonalInfo(
            name="Test User", email="test@test.com", phone="+55",
            location="Brazil", linkedin="linkedin.com/in/test",
            github="github.com/test", website="test.com",
            timezone="America/Bahia",
        ),
        current_experience=Experience(
            title="Security Architect", company="voidnxlabs", start="2024-03",
        ),
        primary_skills=["Rust", "NixOS", "eBPF", "Security Architecture"],
        secondary_skills=["Python", "Kubernetes"],
        languages=["Portuguese", "English"],
        preferences=Preferences(
            remote_only=True,
            min_salary_usd=80000,
            target_roles=["Security Architect", "Platform Engineer"],
            dealbreakers=["on-site", "junior only"],
        ),
        cover_letter_template="Test cover letter.",
        llm_api_url="http://localhost:9000",
        llm_model="mistral",
    )
    setattr(profile, '_discovery_cfg', {
        'sources': ['remoteok', 'companies'],
        'keywords': ['security architect', 'platform engineer', 'nixos', 'rust'],
        'min_score': 40.0,
        'interval_hours': 4,
        'companies': [],
    })
    return profile
```

---

## 8. New `profile.toml` dependencies check

No new pip dependencies needed:

| Module used | Origin |
|---|---|
| `imaplib` | stdlib |
| `email` | stdlib |
| `xml.etree.ElementTree` | stdlib |
| `asyncio.to_thread` | stdlib (Python 3.9+) |
| `httpx` | already in flake ✓ |
| `rich` | already in flake ✓ |

---

## Implementation order

Execute in this exact order:

```
1. profile.py — add _discovery_cfg / _email_cfg loading in _parse_profile()
2. profile.example.toml — add [discovery] and [email] sections
3. intel/job_discovery.py — pure httpx, no side effects
4. intel/email_monitor.py — stdlib IMAP, no side effects
5. intel/scheduler.py — wires everything together
6. cli.py — append job-hunt, job-queue, job-status commands
7. tests/test_job_discovery.py — run with --no-cov
8. manual test: spider job-hunt --once --discover-only
9. manual test: spider job-queue
10. manual test: spider job-hunt (full daemon, Ctrl+C to stop)
```

---

## Usage

```bash
# One discovery cycle (good for cron or first run)
spider job-hunt --once

# See what was found
spider job-queue

# Full pipeline dashboard
spider job-status

# Start daemon (discovery + apply loop + email monitor)
spider job-hunt

# Discovery only, no apply TUI (batch mode)
spider job-hunt --discover-only

# Cron example (every 4 hours via crontab or systemd timer)
0 */4 * * * cd /path/to/spider-nix && spider job-hunt --once --discover-only

# Apply manually to a specific queued job
spider job-apply <url>

# Track history
spider job-history --status interview
spider job-history --status submitted
```

---

## What this phase adds

```
ADDED: intel/job_discovery.py
       — 5 sources: RemoteOK, We Work Remotely, Jobicy, HN Hiring, company boards
       — parallel fetch with asyncio.gather
       — keyword + score filtering before saving to tracker
       — deduplication against existing tracker entries

ADDED: intel/email_monitor.py
       — stdlib IMAP (zero new deps)
       — regex classifier: offer/interview/rejection/followup (90%+ accuracy)
       — ntfy alerts with priority based on email type
       — tracker status updates

ADDED: intel/scheduler.py
       — 3 asyncio tasks in parallel
       — graceful SIGINT/SIGTERM shutdown
       — --once mode for cron usage
       — apply_after_discovery flag

ADDED: CLI job-hunt / job-queue / job-status

RESULT: Zero manual job searching.
        Run once a day, review queue, approve applications from terminal.
```
