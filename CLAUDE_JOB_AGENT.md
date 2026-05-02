# Job Agent — Spider-Nix Extension Plan

## Context

Spider-nix is an enterprise-grade OSINT/web crawler built in Python 3.13 + asyncio,
running on NixOS with a Nix flake dev environment. It already has:

- `BrowserCrawler` (Playwright + stealth + uTLS Go proxy)
- `FormAnalyzer` (HTML form field extraction + purpose detection)
- `JobAnalyzer` + `CareerPageFinder` in `src/spider_nix/intel/jobs.py`
- `SqliteStorage` with FTS5
- `StealthEngine` (canvas/WebGL/navigator spoofing)
- `StrategySelector` (epsilon-greedy per-domain learning)
- `FailureClassifier` (429/bot/CAPTCHA detection)
- `spider-network-proxy` (Go uTLS TLS fingerprint rotation)

The goal is to build a **job application agent** on top of this existing infrastructure.
Zero new crawling infrastructure. Only new intel/ modules, a profile system, ATS adapters,
an approval gate, and a new CLI command.

---

## Objective

When the user finds a job posting URL (LinkedIn Easy Apply excluded — handled manually),
they run:

```bash
spider job-apply https://boards.greenhouse.io/company/jobs/123456
```

The agent:
1. Detects the ATS platform
2. Scrapes the job description
3. Sends description + user profile to ml-ops-api (local LLM) for field mapping + cover letter
4. Uses BrowserCrawler + FormAnalyzer to fill the form
5. Takes a screenshot and pauses for human approval (Telegram or CLI confirm)
6. On approval: submits and logs to SQLite
7. Sends notification (Telegram webhook)

---

## File Structure

Create the following files. Do NOT modify existing spider-nix files unless
adding a single import or CLI command registration.

```
src/spider_nix/intel/
  profile.py            # Profile dataclass + TOML loader
  personal_scorer.py    # Personal criteria scorer (replaces generic JobAnalyzer scoring)
  llm_mapper.py         # LLM field mapping + cover letter generation
  approval_gate.py      # Human-in-the-loop gate (Telegram + CLI fallback)
  tracker.py            # SQLite application history
  ats/
    __init__.py
    detector.py         # ATS platform detection from URL/DOM
    greenhouse.py       # Greenhouse adapter
    lever.py            # Lever adapter
    ashby.py            # Ashby adapter
    workday.py          # Workday adapter (best-effort)
    generic.py          # Generic adapter: FormAnalyzer → LLM field mapping

profile.toml            # User's canonical profile (repo root, gitignored)
profile.example.toml    # Example profile template (committed)
```

---

## 1. `profile.toml` schema

```toml
[personal]
name = ""
email = ""
phone = ""
location = "Feira de Santana, BA, Brazil"
linkedin = ""
github = "github.com/marcosfpina"
website = "voidnx.com"
timezone = "America/Bahia"

[experience.current]
title = "Security Architect & Infrastructure Engineer"
company = "voidnxlabs (Open Source)"
start = "2024-03"
description = """
Solo architect building voidnxlabs — a universal protocol ecosystem of
interconnected open-source infrastructure projects in Rust on NixOS.
"""

[skills]
primary = ["Rust", "NixOS", "eBPF", "Security Architecture", "DevSecOps"]
secondary = ["Python", "Kubernetes", "GCP", "Azure", "OPA", "Go"]
languages = ["Portuguese (native)", "English (professional)"]

[preferences]
remote_only = true
min_salary_usd = 80000
target_roles = [
  "Security Architect",
  "Platform Engineer",
  "DevSecOps Engineer",
  "Infrastructure Engineer",
  "MLOps Engineer",
]
dealbreakers = ["on-site", "brazil only", ".net only", "junior only"]

[cover_letter]
template = """
I build systems where guarantees are structural, not contractual.

At voidnxlabs, I've architected {ecosystem_description} — a {tech_stack} stack
where security enforcement happens at the kernel and protocol level, not as
an afterthought. {company_hook}

What draws me to {company}: {why_company}. I'd bring the same philosophy
to {role}: measurable, verifiable, and reproducible by design.
"""

[llm]
# Local ml-ops-api endpoint
api_url = "http://localhost:9000"
model = "mistral"  # or whatever is loaded in ml-ops-api
```

---

## 2. `src/spider_nix/intel/profile.py`

```python
"""User profile loader for job application agent."""

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class PersonalInfo:
    name: str
    email: str
    phone: str
    location: str
    linkedin: str
    github: str
    website: str
    timezone: str


@dataclass
class Experience:
    title: str
    company: str
    start: str
    description: str = ""


@dataclass
class Preferences:
    remote_only: bool
    min_salary_usd: int
    target_roles: list[str]
    dealbreakers: list[str]


@dataclass
class Profile:
    personal: PersonalInfo
    current_experience: Experience
    primary_skills: list[str]
    secondary_skills: list[str]
    languages: list[str]
    preferences: Preferences
    cover_letter_template: str
    llm_api_url: str
    llm_model: str

    def as_context_string(self) -> str:
        """Serialize profile as LLM context string."""
        return f"""
Name: {self.personal.name}
Location: {self.personal.location}
Current Role: {self.current_experience.title} at {self.current_experience.company}
Primary Skills: {', '.join(self.primary_skills)}
Secondary Skills: {', '.join(self.secondary_skills)}
GitHub: {self.personal.github}
Website: {self.personal.website}
LinkedIn: {self.personal.linkedin}
Remote Only: {self.preferences.remote_only}
Min Salary (USD): {self.preferences.min_salary_usd}
Target Roles: {', '.join(self.preferences.target_roles)}
Dealbreakers: {', '.join(self.preferences.dealbreakers)}
        """.strip()


def load_profile(path: Path | str | None = None) -> Profile:
    """
    Load profile from TOML file.

    Looks in:
    1. Explicit path argument
    2. SPIDER_PROFILE env var
    3. ./profile.toml (repo root)
    4. ~/.config/spider-nix/profile.toml
    """
    import os

    candidates = []
    if path:
        candidates.append(Path(path))

    env_path = os.environ.get("SPIDER_PROFILE")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(Path("profile.toml"))
    candidates.append(Path.home() / ".config" / "spider-nix" / "profile.toml")

    for candidate in candidates:
        if candidate.exists():
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            return _parse_profile(data)

    raise FileNotFoundError(
        "No profile.toml found. Copy profile.example.toml to profile.toml and fill it in."
    )


def _parse_profile(data: dict) -> Profile:
    p = data["personal"]
    exp = data["experience"]["current"]
    skills = data["skills"]
    prefs = data["preferences"]
    cl = data["cover_letter"]
    llm = data.get("llm", {})

    return Profile(
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
```

---

## 3. `src/spider_nix/intel/personal_scorer.py`

```python
"""Personal job scoring criteria on top of JobAnalyzer."""

from .jobs import JobOpportunity
from .profile import Profile


def score_opportunity(opp: JobOpportunity, profile: Profile) -> tuple[float, list[str]]:
    """
    Score a job opportunity against personal profile.

    Returns (score, reasons[]) where score is 0.0-100.0.
    """
    score = 0.0
    reasons = []
    content = (
        f"{opp.title or ''} {opp.remote_policy or ''} {' '.join(opp.tech_stack)}"
    ).lower()

    # Dealbreaker check — return immediately
    for db in profile.preferences.dealbreakers:
        if db.lower() in content:
            return 0.0, [f"DEALBREAKER: {db}"]

    # Remote
    if opp.remote_policy and "remote" in opp.remote_policy.lower():
        score += 30.0
        reasons.append("Remote ✓")
    elif profile.preferences.remote_only:
        score -= 50.0
        reasons.append("Not remote (penalty)")

    # Primary skills match
    matched_primary = [s for s in profile.primary_skills if s.lower() in content]
    skill_score = len(matched_primary) * 8.0
    score += min(skill_score, 40.0)
    if matched_primary:
        reasons.append(f"Primary skills: {', '.join(matched_primary)}")

    # Secondary skills
    matched_secondary = [s for s in profile.secondary_skills if s.lower() in content]
    score += len(matched_secondary) * 3.0
    if matched_secondary:
        reasons.append(f"Secondary skills: {', '.join(matched_secondary)}")

    # Target role match
    for role in profile.preferences.target_roles:
        if role.lower() in content:
            score += 15.0
            reasons.append(f"Role match: {role}")
            break

    # Salary
    if opp.salary_range:
        reasons.append(f"Salary listed: {opp.salary_range}")
        score += 5.0

    return min(score, 100.0), reasons
```

---

## 4. `src/spider_nix/intel/llm_mapper.py`

```python
"""
LLM-powered field mapping and cover letter generation.

Calls ml-ops-api (local) or falls back to direct API call.
Uses the profile + job description to generate:
- A customized cover letter
- A field mapping dict: { detected_field_name: value_from_profile }
- Answers to custom application questions
"""

import json
import httpx
from .profile import Profile


FIELD_MAPPING_PROMPT = """
You are a job application assistant. Given a job description and a candidate profile,
generate a JSON object with:

1. "cover_letter": A 2-paragraph cover letter in the candidate's voice. 
   Direct, technical, no fluff. Mention specific tech from the job description.
   Do NOT use phrases like "I am passionate about" or "I am excited to".

2. "field_mapping": A dict mapping common application form field names to values
   from the candidate profile. Common field names include:
   first_name, last_name, email, phone, linkedin_url, github_url, website,
   resume_url, location, years_of_experience, cover_letter, salary_expectation

3. "custom_answers": A dict for any other questions you detect in the job description,
   with concise professional answers from the candidate's perspective.

Return ONLY valid JSON. No markdown, no preamble.

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
{profile_context}
"""


async def generate_mapping(
    job_description: str,
    profile: Profile,
    timeout: float = 60.0,
) -> dict:
    """
    Call local LLM to generate field mapping + cover letter.

    Returns dict with keys: cover_letter, field_mapping, custom_answers
    Falls back to minimal mapping if LLM unavailable.
    """
    prompt = FIELD_MAPPING_PROMPT.format(
        job_description=job_description[:4000],  # truncate for context window
        profile_context=profile.as_context_string(),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try OpenAI-compatible endpoint (ml-ops-api / llama.cpp server)
            response = await client.post(
                f"{profile.llm_api_url}/v1/chat/completions",
                json={
                    "model": profile.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            # Strip any accidental markdown fences
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(content)

    except Exception as e:
        # Fallback: minimal mapping from profile directly
        return _fallback_mapping(profile)


def _fallback_mapping(profile: Profile) -> dict:
    """Minimal mapping when LLM is unavailable."""
    p = profile.personal
    return {
        "cover_letter": profile.cover_letter_template,
        "field_mapping": {
            "first_name": p.name.split()[0],
            "last_name": p.name.split()[-1],
            "full_name": p.name,
            "email": p.email,
            "phone": p.phone,
            "location": p.location,
            "linkedin_url": p.linkedin,
            "github_url": p.github,
            "website": p.website,
        },
        "custom_answers": {},
    }
```

---

## 5. `src/spider_nix/intel/ats/detector.py`

```python
"""ATS platform detection from URL and page content."""

from enum import Enum
from urllib.parse import urlparse


class ATSPlatform(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    BAMBOOHR = "bamboohr"
    GENERIC = "generic"


ATS_URL_PATTERNS: dict[str, ATSPlatform] = {
    "boards.greenhouse.io": ATSPlatform.GREENHOUSE,
    "greenhouse.io": ATSPlatform.GREENHOUSE,
    "jobs.lever.co": ATSPlatform.LEVER,
    "lever.co": ATSPlatform.LEVER,
    "jobs.ashbyhq.com": ATSPlatform.ASHBY,
    "ashbyhq.com": ATSPlatform.ASHBY,
    "myworkdayjobs.com": ATSPlatform.WORKDAY,
    "workday.com": ATSPlatform.WORKDAY,
    "careers.smartrecruiters.com": ATSPlatform.SMARTRECRUITERS,
    "smartrecruiters.com": ATSPlatform.SMARTRECRUITERS,
    "bamboohr.com": ATSPlatform.BAMBOOHR,
}


def detect_from_url(url: str) -> ATSPlatform:
    """Detect ATS platform from URL."""
    netloc = urlparse(url).netloc.lower()
    for pattern, platform in ATS_URL_PATTERNS.items():
        if pattern in netloc:
            return platform
    return ATSPlatform.GENERIC


def detect_from_html(html: str) -> ATSPlatform:
    """Fallback detection from page HTML."""
    html_lower = html.lower()
    if "greenhouse" in html_lower or "grnh.se" in html_lower:
        return ATSPlatform.GREENHOUSE
    if "lever.co" in html_lower:
        return ATSPlatform.LEVER
    if "ashby" in html_lower:
        return ATSPlatform.ASHBY
    if "workday" in html_lower:
        return ATSPlatform.WORKDAY
    return ATSPlatform.GENERIC
```

---

## 6. `src/spider_nix/intel/ats/greenhouse.py`

```python
"""
Greenhouse ATS adapter.

Greenhouse exposes a public JSON API:
  GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}

This gives us the full job description without browser rendering.
The application form is at boards.greenhouse.io/{company}/jobs/{job_id}
"""

import re
import httpx
from playwright.async_api import Page


async def fetch_job_description(url: str) -> str:
    """
    Fetch job description via Greenhouse public API.

    Parses company slug and job ID from URL.
    Falls back to page scraping if API fails.
    """
    # Extract company and job_id from URL patterns:
    # boards.greenhouse.io/{company}/jobs/{job_id}
    # job-boards.greenhouse.io/{company}/jobs/{job_id}
    match = re.search(r'greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    if not match:
        return ""

    company = match.group(1)
    job_id = match.group(2)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"
            )
            resp.raise_for_status()
            data = resp.json()
            # Strip HTML tags from content
            content = data.get("content", "")
            clean = re.sub(r'<[^>]+>', ' ', content)
            title = data.get("title", "")
            return f"{title}\n\n{clean}"
    except Exception:
        return ""


GREENHOUSE_SELECTORS = {
    "first_name": "#first_name",
    "last_name": "#last_name",
    "email": "#email",
    "phone": "#phone",
    "location": "#job_application_location",
    "resume": "#resume",
    "cover_letter_text": "#cover_letter",
    "linkedin": "input[name*='linkedin'], input[id*='linkedin']",
    "github": "input[name*='github'], input[id*='github']",
    "website": "input[name*='website'], input[name*='portfolio']",
    "submit": "input[type='submit'], button[type='submit']",
}


async def fill_form(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """
    Fill Greenhouse application form.

    Returns True if form appears filled successfully.
    Raises on critical failures.
    """
    mapping_with_cl = {**field_mapping, "cover_letter_text": cover_letter}

    for field_key, selector in GREENHOUSE_SELECTORS.items():
        if field_key == "submit":
            continue

        value = mapping_with_cl.get(field_key) or field_mapping.get(field_key)
        if not value:
            continue

        try:
            element = await page.query_selector(selector)
            if element:
                input_type = await element.get_attribute("type")
                if input_type == "file":
                    continue  # Skip resume upload — handle separately
                await element.click()
                await element.fill(str(value))
        except Exception:
            continue  # Non-critical: skip missing optional fields

    return True


async def get_resume_upload_selector(page: Page) -> str | None:
    """Get the resume upload input selector if present."""
    selectors = ["#resume", "input[type='file'][name*='resume']", "input[type='file']"]
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            return sel
    return None
```

---

## 7. `src/spider_nix/intel/ats/lever.py`

```python
"""
Lever ATS adapter.

Lever exposes public postings API:
  GET https://api.lever.co/v0/postings/{company}/{job_id}

Application form is at jobs.lever.co/{company}/{job_id}/apply
"""

import re
import httpx
from playwright.async_api import Page


async def fetch_job_description(url: str) -> str:
    """Fetch job description via Lever public API."""
    match = re.search(r'lever\.co/([^/]+)/([a-f0-9-]{36})', url)
    if not match:
        return ""

    company = match.group(1)
    job_id = match.group(2)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.lever.co/v0/postings/{company}/{job_id}"
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", "")
            description = data.get("descriptionPlain", "")
            lists = data.get("lists", [])
            extra = " ".join(item.get("content", "") for item in lists)
            return f"{text}\n\n{description}\n\n{extra}"
    except Exception:
        return ""


LEVER_SELECTORS = {
    "first_name": "input[name='name']",       # Lever uses full name
    "email": "input[name='email']",
    "phone": "input[name='phone']",
    "org": "input[name='org']",               # Current company
    "linkedin": "input[name='urls[LinkedIn]']",
    "github": "input[name='urls[GitHub]']",
    "website": "input[name='urls[Portfolio]'], input[name='urls[Other]']",
    "cover_letter_text": "textarea[name='comments']",
    "submit": "button[type='submit']",
}


async def fill_form(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """Fill Lever application form."""
    # Lever uses "name" for full name
    full_mapping = {
        **field_mapping,
        "first_name": field_mapping.get("full_name") or (
            f"{field_mapping.get('first_name', '')} {field_mapping.get('last_name', '')}".strip()
        ),
        "cover_letter_text": cover_letter,
        "org": field_mapping.get("company", "voidnxlabs"),
    }

    for field_key, selector in LEVER_SELECTORS.items():
        if field_key == "submit":
            continue

        value = full_mapping.get(field_key)
        if not value:
            continue

        try:
            element = await page.query_selector(selector)
            if element:
                await element.click()
                await element.fill(str(value))
        except Exception:
            continue

    return True
```

---

## 8. `src/spider_nix/intel/ats/generic.py`

```python
"""
Generic ATS adapter using FormAnalyzer + LLM field mapping.

Used when ATS is unknown. Extracts all form fields via FormAnalyzer,
sends them to LLM to map against profile, then fills via Playwright.
"""

import httpx
from playwright.async_api import Page
from ...osint.web_discovery import FormAnalyzer
from ..llm_mapper import generate_mapping
from ..profile import Profile


async def fetch_job_description(page: Page) -> str:
    """Extract job description from current page via text content."""
    try:
        # Get all visible text
        text = await page.evaluate("""
            () => {
                const selectors = [
                    '[class*="description"]',
                    '[class*="job-detail"]',
                    '[class*="posting"]',
                    'article',
                    'main',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.textContent.length > 200) {
                        return el.textContent.trim();
                    }
                }
                return document.body.textContent.trim();
            }
        """)
        return text[:5000]
    except Exception:
        return ""


async def fill_form(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """
    Fill generic form using LLM-guided field matching.

    Strategy:
    1. Get all input/textarea elements and their labels
    2. For each field, use fuzzy matching against field_mapping keys
    3. Fill matched fields
    """
    # Get all form fields with their labels/names/placeholders
    fields = await page.evaluate("""
        () => {
            const inputs = document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="file"]), textarea'
            );
            return Array.from(inputs).map(el => ({
                tag: el.tagName,
                type: el.type || 'text',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                label: (() => {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    return label ? label.textContent.trim() : '';
                })(),
                selector: el.id ? `#${el.id}` : `[name="${el.name}"]`,
            }));
        }
    """)

    full_mapping = {**field_mapping, "cover_letter": cover_letter}

    for field in fields:
        # Build a search key from all field identifiers
        search_key = " ".join([
            field.get("name", ""),
            field.get("id", ""),
            field.get("placeholder", ""),
            field.get("label", ""),
        ]).lower()

        # Fuzzy match against our known field keys
        matched_value = _fuzzy_match(search_key, full_mapping)
        if not matched_value:
            continue

        try:
            selector = field["selector"]
            element = await page.query_selector(selector)
            if element:
                await element.click()
                await element.fill(str(matched_value))
        except Exception:
            continue

    return True


def _fuzzy_match(search_key: str, mapping: dict) -> str | None:
    """Match a field's search key against profile mapping keys."""
    FIELD_ALIASES = {
        "first_name": ["first", "fname", "given"],
        "last_name": ["last", "lname", "surname", "family"],
        "full_name": ["full name", "name", "your name"],
        "email": ["email", "e-mail", "mail"],
        "phone": ["phone", "telephone", "mobile", "cell"],
        "location": ["location", "city", "where are you", "current location"],
        "linkedin_url": ["linkedin"],
        "github_url": ["github"],
        "website": ["website", "portfolio", "personal site"],
        "cover_letter": ["cover letter", "why", "motivation", "message", "tell us"],
    }

    for field_key, aliases in FIELD_ALIASES.items():
        if any(alias in search_key for alias in aliases):
            value = mapping.get(field_key)
            if value:
                return value

    return None
```

---

## 9. `src/spider_nix/intel/approval_gate.py`

```python
"""
Human-in-the-loop approval gate.

Before submitting any application:
1. Takes a screenshot of filled form
2. Sends to Telegram (if configured) or prints path to CLI
3. Waits for approval: y/n from CLI or Telegram inline keyboard
4. Returns True (approved) or False (rejected)

CRITICAL: Nothing is submitted without human approval.
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import Page

import httpx
from rich.console import Console
from rich.prompt import Confirm

console = Console()


async def request_approval(
    page: Page,
    job_url: str,
    company: str,
    role: str,
    screenshot_dir: Path = Path("screenshots"),
) -> bool:
    """
    Gate the application submission behind human approval.

    Returns True if approved, False if rejected.
    """
    # Take screenshot of filled form
    screenshot_dir.mkdir(exist_ok=True)
    screenshot_path = screenshot_dir / f"apply_{company}_{role}.png".replace(" ", "_")

    await page.screenshot(path=str(screenshot_path), full_page=True)
    console.print(f"\n[cyan]📸 Screenshot saved:[/] {screenshot_path}")

    # Try Telegram if configured
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        approved = await _telegram_approval(
            token=telegram_token,
            chat_id=telegram_chat_id,
            screenshot_path=screenshot_path,
            job_url=job_url,
            company=company,
            role=role,
        )
        return approved

    # CLI fallback
    console.print(f"\n[bold yellow]⚠ Ready to submit application:[/]")
    console.print(f"  Company : {company}")
    console.print(f"  Role    : {role}")
    console.print(f"  URL     : {job_url}")
    console.print(f"  Screenshot: {screenshot_path}")
    console.print("\n[dim]Review the screenshot before approving.[/]")

    return Confirm.ask("\n[bold]Submit this application?[/]", default=False)


async def _telegram_approval(
    token: str,
    chat_id: str,
    screenshot_path: Path,
    job_url: str,
    company: str,
    role: str,
    timeout: float = 300.0,  # 5 minutes to respond
) -> bool:
    """
    Send screenshot to Telegram and wait for inline keyboard response.

    Sends:
    - Screenshot of filled form
    - Job details caption
    - [✅ Submit] [❌ Skip] inline keyboard
    """
    base = f"https://api.telegram.org/bot{token}"
    caption = f"🎯 *{role}* @ {company}\n{job_url}\n\nReview the filled form above."

    # Send photo with inline keyboard
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(screenshot_path, "rb") as photo:
            resp = await client.post(
                f"{base}/sendPhoto",
                data={
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown",
                    "reply_markup": '{"inline_keyboard": [[{"text": "✅ Submit", "callback_data": "approve"}, {"text": "❌ Skip", "callback_data": "reject"}]]}',
                },
                files={"photo": photo},
            )
        message_id = resp.json().get("result", {}).get("message_id")

    # Poll for callback
    last_update_id = 0
    deadline = asyncio.get_event_loop().time() + timeout

    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(3)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{base}/getUpdates",
                params={"offset": last_update_id + 1, "timeout": 3},
            )
            updates = resp.json().get("result", [])

            for update in updates:
                last_update_id = update["update_id"]
                callback = update.get("callback_query", {})
                if callback:
                    data = callback.get("data", "")
                    # Acknowledge callback
                    await client.post(
                        f"{base}/answerCallbackQuery",
                        json={"callback_query_id": callback["id"]},
                    )
                    if data == "approve":
                        console.print("[green]✅ Approved via Telegram[/]")
                        return True
                    elif data == "reject":
                        console.print("[red]❌ Rejected via Telegram[/]")
                        return False

    console.print("[yellow]⚠ Approval timeout — skipping[/]")
    return False
```

---

## 10. `src/spider_nix/intel/tracker.py`

```python
"""
Application history tracker using SQLite.

Tracks every application attempt with status, screenshots, and events.
"""

import aiosqlite
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    ats_platform TEXT,
    status TEXT DEFAULT 'pending',
    -- status: pending | submitted | rejected | interview | ghosted | offer
    applied_at DATETIME,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    screenshot_path TEXT,
    cover_letter TEXT,
    field_mapping TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id),
    event_type TEXT,
    -- event_type: applied | email_received | interview_scheduled | rejected | offer
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_data TEXT
);

CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_company ON applications(company);
"""


@dataclass
class Application:
    url: str
    company: str
    role: str
    ats_platform: str
    status: str = "pending"
    applied_at: datetime | None = None
    screenshot_path: str | None = None
    cover_letter: str | None = None
    notes: str | None = None


class ApplicationTracker:
    def __init__(self, db_path: Path = Path("applications.db")):
        self.db_path = db_path
        self._initialized = False

    async def _init(self):
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        self._initialized = True

    async def record_application(self, app: Application) -> int:
        """Insert or update application record. Returns row id."""
        import json
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO applications (url, company, role, ats_platform, status,
                    applied_at, screenshot_path, cover_letter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    status = excluded.status,
                    last_updated = CURRENT_TIMESTAMP
                """,
                (
                    app.url, app.company, app.role, app.ats_platform,
                    app.status, app.applied_at, app.screenshot_path, app.cover_letter,
                )
            )
            await db.commit()
            return cursor.lastrowid

    async def update_status(self, url: str, status: str, notes: str | None = None):
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE applications SET status=?, notes=?, last_updated=CURRENT_TIMESTAMP WHERE url=?",
                (status, notes, url)
            )
            await db.commit()

    async def list_applications(self, status: str | None = None) -> list[dict]:
        await self._init()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    "SELECT * FROM applications WHERE status=? ORDER BY applied_at DESC",
                    (status,)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM applications ORDER BY applied_at DESC"
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
```

---

## 11. Main orchestrator + CLI command

Add to `src/spider_nix/cli.py` — import the new modules and register a new command.
Do NOT restructure the existing CLI, just append.

```python
# Add these imports at the top of cli.py
from .intel.profile import load_profile
from .intel.personal_scorer import score_opportunity
from .intel.llm_mapper import generate_mapping
from .intel.approval_gate import request_approval
from .intel.tracker import ApplicationTracker, Application
from .intel.ats.detector import detect_from_url, ATSPlatform

# Add this command to the existing app typer instance:

@app.command("job-apply")
def job_apply(
    url: str = typer.Argument(..., help="Job posting URL"),
    profile_path: Optional[Path] = typer.Option(None, "--profile", "-p", help="Path to profile.toml"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fill form but do not submit"),
    headless: bool = typer.Option(True, "--headless", help="Run browser headless"),
    resume: Optional[Path] = typer.Option(None, "--resume", "-r", help="Path to resume PDF"),
):
    """
    🎯 Auto-fill and submit a job application.

    Detects ATS, maps your profile to form fields via LLM,
    fills the form, takes a screenshot, waits for your approval,
    then submits.

    Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID for mobile approval.
    """
    console.print(f"\n[bold]🎯 Job Apply Agent[/]\n")

    async def run():
        # 1. Load profile
        try:
            profile = load_profile(profile_path)
            console.print(f"[green]✓[/] Profile loaded: {profile.personal.name}")
        except FileNotFoundError as e:
            console.print(f"[red]✗ {e}[/]")
            raise typer.Exit(1)

        # 2. Detect ATS
        ats = detect_from_url(url)
        console.print(f"[cyan]ATS detected:[/] {ats.value}")

        # 3. Import appropriate adapter
        if ats == ATSPlatform.GREENHOUSE:
            from .intel.ats.greenhouse import fetch_job_description, fill_form, GREENHOUSE_SELECTORS as _s
        elif ats == ATSPlatform.LEVER:
            from .intel.ats.lever import fetch_job_description, fill_form
        else:
            from .intel.ats.generic import fetch_job_description, fill_form

        # 4. Fetch job description (API if available)
        console.print("[cyan]Fetching job description...[/]")
        job_description = await fetch_job_description(url)

        # 5. LLM field mapping + cover letter
        console.print("[cyan]Generating field mapping via LLM...[/]")
        mapping_result = await generate_mapping(job_description, profile)
        field_mapping = mapping_result.get("field_mapping", {})
        cover_letter = mapping_result.get("cover_letter", profile.cover_letter_template)

        console.print(f"[green]✓[/] Cover letter generated ({len(cover_letter)} chars)")

        # 6. Launch browser and fill form
        from playwright.async_api import async_playwright

        tracker = ApplicationTracker()

        async with async_playwright() as p:
            from .config import CrawlerConfig
            from .browser import BrowserCrawler

            config = CrawlerConfig(use_browser=True, headless=headless)
            crawler = BrowserCrawler(config=config, use_network_proxy=True)

            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent=crawler.stealth.get_user_agent(),
                viewport={"width": 1440, "height": 900},
            )
            await context.add_init_script(crawler.stealth.get_playwright_stealth_script())
            page = await context.new_page()

            console.print(f"[cyan]Navigating to:[/] {url}")
            await page.goto(url, wait_until="networkidle")

            # Fill form
            console.print("[cyan]Filling form...[/]")
            await fill_form(page, field_mapping, cover_letter)

            # Upload resume if provided
            if resume and resume.exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(str(resume))
                        console.print(f"[green]✓[/] Resume uploaded: {resume.name}")
                except Exception as e:
                    console.print(f"[yellow]⚠ Resume upload failed: {e}[/]")

            if dry_run:
                # Screenshot only, no submit
                screenshot_path = Path(f"screenshots/dry_run_{url.replace('/', '_')[:40]}.png")
                screenshot_path.parent.mkdir(exist_ok=True)
                await page.screenshot(path=str(screenshot_path), full_page=True)
                console.print(f"\n[yellow]DRY RUN — not submitted[/]")
                console.print(f"[green]Screenshot:[/] {screenshot_path}")
                await browser.close()
                return

            # 7. Approval gate
            company = field_mapping.get("company", urlparse(url).netloc)
            role = job_description[:80] if job_description else url

            approved = await request_approval(
                page=page,
                job_url=url,
                company=company,
                role=role,
            )

            if not approved:
                console.print("[yellow]⚠ Application skipped[/]")
                await browser.close()
                return

            # 8. Submit
            submit_button = await page.query_selector(
                "input[type='submit'], button[type='submit'], button:has-text('Submit'), button:has-text('Apply')"
            )
            if submit_button:
                await submit_button.click()
                await page.wait_for_timeout(3000)
                console.print("[bold green]✅ Application submitted![/]")
            else:
                console.print("[yellow]⚠ Submit button not found — review manually[/]")

            # 9. Track
            from datetime import datetime
            from urllib.parse import urlparse
            app = Application(
                url=url,
                company=company,
                role=role,
                ats_platform=ats.value,
                status="submitted",
                applied_at=datetime.now(),
                cover_letter=cover_letter,
            )
            await tracker.record_application(app)
            console.print(f"[green]✓[/] Logged to applications.db")

            await browser.close()

    from urllib.parse import urlparse
    asyncio.run(run())
```

---

## 12. `src/spider_nix/intel/ats/ashby.py`

Ashby exposes a public API similar to Greenhouse:
```
GET https://api.ashbyhq.com/posting-api/job-board/{company}/published
GET https://api.ashbyhq.com/posting-api/job-board/{company}/application-form?jobPostingId={id}
```

Implement `fetch_job_description` and `fill_form` following the same pattern as greenhouse.py.
Parse the company slug from `jobs.ashbyhq.com/{company}/{job_id}`.

---

## 13. `src/spider_nix/intel/ats/workday.py`

Workday is notoriously difficult. Best-effort approach:
1. Use BrowserCrawler to render the page (Workday is heavy SPA)
2. Use `FormAnalyzer` on the rendered HTML
3. Use generic fill_form with fuzzy matching
4. Flag for manual review if fields don't match

```python
"""Workday ATS adapter — best effort, requires browser rendering."""

from playwright.async_api import Page
from .generic import fetch_job_description, fill_form  # reuse generic

# Workday-specific selectors to try on top of generic
WORKDAY_EXTRA_SELECTORS = {
    "legalName": "input[data-automation-id='legalNameSection_firstName']",
    "lastName": "input[data-automation-id='legalNameSection_lastName']",
    "email": "input[data-automation-id='email']",
    "phone": "input[data-automation-id='phone']",
    "coverLetter": "textarea[data-automation-id='coverLetter']",
}

async def fill_form_workday(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """Try Workday-specific selectors, fall back to generic."""
    full_mapping = {
        **field_mapping,
        "legalName": field_mapping.get("first_name", ""),
        "lastName": field_mapping.get("last_name", ""),
        "coverLetter": cover_letter,
    }

    for field_key, selector in WORKDAY_EXTRA_SELECTORS.items():
        value = full_mapping.get(field_key)
        if not value:
            continue
        try:
            el = await page.query_selector(selector)
            if el:
                await el.click()
                await el.fill(str(value))
        except Exception:
            continue

    # Also run generic as fallback
    await fill_form(page, field_mapping, cover_letter)
    return True
```

---

## 14. CLI command for application history

Add to `cli.py`:

```python
@app.command("job-history")
def job_history(
    status: Optional[str] = typer.Option(None, "--status", "-s",
        help="Filter by status: pending|submitted|rejected|interview|offer"),
):
    """📋 Show application history."""

    async def run():
        tracker = ApplicationTracker()
        apps = await tracker.list_applications(status)

        if not apps:
            console.print("[yellow]No applications found[/]")
            return

        table = Table(title=f"Applications ({len(apps)})")
        table.add_column("Company", style="cyan")
        table.add_column("Role", style="white", max_width=40)
        table.add_column("ATS", style="dim")
        table.add_column("Status", style="yellow")
        table.add_column("Applied", style="dim")

        STATUS_COLORS = {
            "submitted": "green",
            "rejected": "red",
            "interview": "bright_green",
            "offer": "bold bright_green",
            "ghosted": "dim",
            "pending": "yellow",
        }

        for a in apps:
            color = STATUS_COLORS.get(a["status"], "white")
            table.add_row(
                a["company"] or "-",
                (a["role"] or "")[:40],
                a["ats_platform"] or "-",
                f"[{color}]{a['status']}[/]",
                a["applied_at"][:10] if a["applied_at"] else "-",
            )

        console.print(table)

    asyncio.run(run())
```

---

## 15. Environment variables

Document in `.env.example` (do NOT commit actual values):

```bash
# Telegram approval gate (optional but recommended)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Profile location (optional — defaults to ./profile.toml)
SPIDER_PROFILE=/path/to/profile.toml

# ml-ops-api (override profile.toml setting)
LLM_API_URL=http://localhost:9000
LLM_MODEL=mistral
```

Add `profile.toml` and `.env` to `.gitignore`.

---

## 16. Tests

Create `tests/test_job_agent.py`:

```python
"""Tests for job agent modules."""
import pytest
from spider_nix.intel.ats.detector import detect_from_url, ATSPlatform
from spider_nix.intel.personal_scorer import score_opportunity
from spider_nix.intel.jobs import JobOpportunity


def test_ats_detection():
    assert detect_from_url("https://boards.greenhouse.io/acme/jobs/123") == ATSPlatform.GREENHOUSE
    assert detect_from_url("https://jobs.lever.co/acme/abc-123") == ATSPlatform.LEVER
    assert detect_from_url("https://jobs.ashbyhq.com/acme/123") == ATSPlatform.ASHBY
    assert detect_from_url("https://acme.myworkdayjobs.com/en-US/jobs") == ATSPlatform.WORKDAY
    assert detect_from_url("https://careers.example.com/jobs/123") == ATSPlatform.GENERIC


def test_personal_scorer_dealbreaker(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp", url="https://example.com",
        remote_policy="on-site", tech_stack=["Rust", "NixOS"]
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert score == 0.0
    assert any("DEALBREAKER" in r for r in reasons)


def test_personal_scorer_good_match(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp", url="https://example.com",
        remote_policy="Remote", tech_stack=["Rust", "NixOS", "eBPF"],
        title="Senior Security Architect"
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert score > 70.0


@pytest.fixture
def mock_profile():
    from spider_nix.intel.profile import Profile, PersonalInfo, Experience, Preferences
    return Profile(
        personal=PersonalInfo(
            name="Test User", email="test@test.com", phone="+55",
            location="Brazil", linkedin="", github="github.com/test",
            website="test.com", timezone="America/Bahia"
        ),
        current_experience=Experience(title="Security Architect", company="voidnxlabs", start="2024"),
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
```

---

## Implementation order

Execute in this exact order:

1. `profile.example.toml` + `profile.py` — foundation, everything depends on it
2. `ats/detector.py` — trivial, needed everywhere
3. `personal_scorer.py` — no async, easy to test
4. `llm_mapper.py` — test with ml-ops-api running locally
5. `tracker.py` — SQLite, test independently
6. `ats/greenhouse.py` + `ats/lever.py` — cover 80% of remote jobs
7. `ats/generic.py` — fallback, uses existing FormAnalyzer
8. `ats/ashby.py` + `ats/workday.py` — secondary platforms
9. `approval_gate.py` — requires TELEGRAM_BOT_TOKEN or CLI fallback
10. CLI commands in `cli.py` (`job-apply`, `job-history`)
11. Tests

---

## Constraints

- Do NOT modify existing spider-nix modules except `cli.py` (import + command append only)
- Do NOT add new dependencies to `flake.nix` without listing them here first
  - `tomllib` is stdlib (Python 3.11+) ✓
  - `aiosqlite` already in flake ✓  
  - `httpx` already in flake ✓
  - `playwright` already in flake ✓
  - No new pip dependencies needed
- All async code must use `asyncio`, not `trio`
- Type hints required on all public functions
- `profile.toml` must be in `.gitignore`
- Human approval gate is non-negotiable — never auto-submit

---

## Usage after implementation

```bash
# Copy and fill profile
cp profile.example.toml profile.toml
$EDITOR profile.toml

# Test with dry run first
spider job-apply https://boards.greenhouse.io/cloudflare/jobs/123456 --dry-run

# Real application with Telegram approval
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
spider job-apply https://boards.greenhouse.io/cloudflare/jobs/123456 --resume ~/resume.pdf

# Check history
spider job-history
spider job-history --status submitted
```
