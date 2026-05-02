# Job Agent — Phase 2: Approval Gate + API Submission

## Current state

All previously planned modules are implemented and passing 6/6 tests:

```
✓ intel/profile.py
✓ intel/personal_scorer.py
✓ intel/llm_mapper.py
✓ intel/ats/detector.py
✓ intel/ats/greenhouse.py
✓ intel/ats/lever.py
✓ intel/ats/ashby.py
✓ intel/ats/workday.py
✓ intel/ats/generic.py
✓ intel/tracker.py
✓ cli.py — job-apply + job-history commands
✓ 6/6 tests passing
```

The `approval_gate.py` was stubbed but never fully implemented —
it had a Telegram dependency that has been dropped entirely.

---

## What this document covers

1. **Rewrite `approval_gate.py`** — Rich TUI interactive diff, ntfy as
   parallel notification (optional, non-blocking), zero Telegram, zero browser
2. **API-first submission layer** — submit via HTTP API for Greenhouse/Lever/Ashby
   before ever touching Playwright. Browser headless is last resort only.
3. **Updated `job-apply` orchestration** in `cli.py` to wire the new gate

---

## Design principles

```
1. Terminal is primary interface — no browser windows, ever if avoidable
2. Human approves before ANY submission — non-negotiable
3. API submission first (Greenhouse/Lever/Ashby have public submit endpoints)
4. Browser headless only as fallback for unknown ATS
5. ntfy notification is fire-and-forget — approval always possible from terminal
6. Zero Telegram anywhere in the codebase
```

---

## Submission priority ladder

```python
# This is the mental model — implement it literally:

async def submit(url, mapping, profile):
    ats = detect_from_url(url)

    # Tier 1: pure HTTP API — zero browser, zero Playwright
    if ats == GREENHOUSE:  return await greenhouse_api_submit(url, mapping)
    if ats == LEVER:       return await lever_api_submit(url, mapping)
    if ats == ASHBY:       return await ashby_api_submit(url, mapping)

    # Tier 2: headless browser — no window, no screenshot
    return await browser_submit_headless(url, mapping)
```

Coverage estimate:
```
Greenhouse API  ~40% of remote tech jobs
Lever API       ~25%
Ashby API       ~10%
browser headless remaining (Workday, custom)

→ 75% of applications: pure terminal, zero browser
```

---

## 1. Rewrite `src/spider_nix/intel/approval_gate.py`

Replace the entire file with the following implementation.

```python
"""
Human-in-the-loop approval gate.

Architecture:
- Rich TUI shows full field diff in terminal
- User approves/edits/rejects interactively
- ntfy push notification sent in parallel if NTFY_TOKEN is set
  (notification is informational only — approval is always terminal-first)
- Zero Telegram, zero browser window

Environment variables (all optional):
  NTFY_URL    default: https://ntfy.sh
  NTFY_TOPIC  default: job-agent
  NTFY_TOKEN  if set, enables push notifications
"""

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import httpx
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


@dataclass
class ApprovalContext:
    job_url: str
    company: str
    role: str
    ats_platform: str
    score: float
    score_reasons: list[str]
    field_mapping: dict
    cover_letter: str
    salary_expectation: str | None = None


async def request_approval(ctx: ApprovalContext) -> tuple[bool, dict]:
    """
    Show TUI diff and wait for human approval.

    Returns (approved: bool, final_mapping: dict).
    final_mapping may differ from ctx.field_mapping if user edited fields.

    Fires ntfy notification in background if configured.
    Does NOT wait for ntfy response — terminal is always the gate.
    """
    # Fire ntfy in background — non-blocking
    asyncio.create_task(_ntfy_notify(ctx))

    # Show TUI and get decision
    return await _tui_approval(ctx)


async def _tui_approval(ctx: ApprovalContext) -> tuple[bool, dict]:
    """
    Rich TUI interactive approval.

    Layout:
    ┌─────────────────────────────────────────────────┐
    │  🎯  Cloudflare · Senior Security Architect      │
    │  Score: 94/100 · Remote · Greenhouse             │
    ├─────────────────────────────────────────────────┤
    │  Field              Value                        │
    │  ───────────────    ──────────────────────────  │
    │  first_name         Bello                        │
    │  last_name          Pina                         │
    │  email              [redacted in display]        │
    │  linkedin_url       linkedin.com/in/...          │
    │  github_url         github.com/marcosfpina       │
    │  website            voidnx.com                   │
    │  cover_letter       [2 paragraphs — press v]     │
    │  salary_expectation 120000                       │
    ├─────────────────────────────────────────────────┤
    │  Why this score:                                 │
    │  ✓ Remote  ✓ Rust  ✓ NixOS  ✓ Security Arch     │
    ├─────────────────────────────────────────────────┤
    │  [s] submit  [e] edit field  [v] view CL  [q] skip
    └─────────────────────────────────────────────────┘
    """
    mapping = dict(ctx.field_mapping)
    cover_letter = ctx.cover_letter

    while True:
        console.clear()
        _render_approval_panel(ctx, mapping, cover_letter)

        choice = Prompt.ask(
            "\n[bold cyan]>[/]",
            choices=["s", "e", "v", "q"],
            default="q",
        )

        if choice == "q":
            console.print("[yellow]⊘ Skipped[/]")
            return False, mapping

        elif choice == "s":
            console.print("\n[bold green]✓ Approved — submitting...[/]")
            return True, mapping

        elif choice == "v":
            # View full cover letter
            console.clear()
            console.print(Panel(
                cover_letter,
                title="[bold]Cover Letter[/]",
                border_style="cyan",
                padding=(1, 2),
            ))
            Prompt.ask("\n[dim]Press Enter to go back[/]", default="")

        elif choice == "e":
            # Edit a specific field
            console.print("\n[dim]Available fields:[/]")
            editable = [k for k in mapping if k != "cover_letter"]
            editable.append("cover_letter")

            for i, key in enumerate(editable):
                val = mapping.get(key, cover_letter if key == "cover_letter" else "")
                preview = str(val)[:60] + "..." if len(str(val)) > 60 else str(val)
                console.print(f"  [cyan]{i+1:2}.[/] {key:25} [dim]{preview}[/]")

            field_idx = Prompt.ask("\n[cyan]Field number[/] (or Enter to cancel)", default="")
            if not field_idx.strip():
                continue

            try:
                idx = int(field_idx) - 1
                field_key = editable[idx]
            except (ValueError, IndexError):
                console.print("[red]Invalid selection[/]")
                await asyncio.sleep(1)
                continue

            if field_key == "cover_letter":
                console.print(Panel(cover_letter, title="Current cover letter"))
                new_val = Prompt.ask("[cyan]New cover letter[/] (Enter to keep)")
                if new_val.strip():
                    cover_letter = new_val
            else:
                current = mapping.get(field_key, "")
                new_val = Prompt.ask(
                    f"[cyan]{field_key}[/]",
                    default=str(current),
                )
                mapping[field_key] = new_val


def _render_approval_panel(ctx: ApprovalContext, mapping: dict, cover_letter: str):
    """Render the approval TUI panel."""

    # Header
    score_color = "green" if ctx.score >= 70 else "yellow" if ctx.score >= 40 else "red"
    console.print(Panel(
        f"[bold]{ctx.role}[/] @ [cyan]{ctx.company}[/]  "
        f"[{score_color}]Score: {ctx.score:.0f}/100[/]  "
        f"[dim]{ctx.ats_platform} · {ctx.job_url}[/]",
        border_style=score_color,
        padding=(0, 1),
    ))

    # Field mapping table
    table = Table(box=box.SIMPLE, padding=(0, 1), show_header=True)
    table.add_column("Field", style="cyan", width=25)
    table.add_column("Value", style="white")

    SENSITIVE = {"email", "phone"}

    for key, value in mapping.items():
        if not value:
            continue
        if key == "cover_letter":
            preview = str(value)[:80].replace("\n", " ") + "..."
            table.add_row(key, f"[dim]{preview}[/]")
        elif key in SENSITIVE:
            masked = str(value)[:3] + "***" + str(value)[-4:]
            table.add_row(key, f"[dim]{masked}[/]")
        else:
            table.add_row(key, str(value)[:80])

    console.print(table)

    # Score reasons
    if ctx.score_reasons:
        reasons_text = "  ".join(
            f"[green]✓ {r}[/]" if "✓" not in r and "DEAL" not in r
            else f"[red]✗ {r}[/]"
            for r in ctx.score_reasons
        )
        console.print(Panel(
            reasons_text,
            title="[dim]Score breakdown[/]",
            border_style="dim",
            padding=(0, 1),
        ))

    # Actions
    console.print(
        "\n  [bold cyan][s][/] submit  "
        "[bold cyan][e][/] edit field  "
        "[bold cyan][v][/] view cover letter  "
        "[bold cyan][q][/] skip"
    )


async def _ntfy_notify(ctx: ApprovalContext):
    """
    Fire-and-forget ntfy notification.

    Self-hosted ntfy on your own Brazilian IP — no intermediary.
    Configure via environment:
      NTFY_URL    https://push.voidnx.com
      NTFY_TOPIC  job-agent
      NTFY_TOKEN  tk_xxxxxxxxxxxx

    Notification is informational only.
    It does NOT gate the approval — terminal does.
    """
    ntfy_url = os.environ.get("NTFY_URL", "https://ntfy.sh")
    ntfy_topic = os.environ.get("NTFY_TOPIC", "job-agent")
    ntfy_token = os.environ.get("NTFY_TOKEN")

    if not ntfy_token:
        return  # ntfy not configured, silently skip

    score_emoji = "🟢" if ctx.score >= 70 else "🟡" if ctx.score >= 40 else "🔴"
    message = (
        f"{score_emoji} Score: {ctx.score:.0f}/100\n"
        f"ATS: {ctx.ats_platform}\n"
        f"{ctx.job_url}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{ntfy_url}/{ntfy_topic}",
                content=message.encode(),
                headers={
                    "Authorization": f"Bearer {ntfy_token}",
                    "Title": f"{ctx.role} @ {ctx.company}",
                    "Tags": "briefcase",
                    "Priority": "default",
                    "Actions": f"view, Abrir vaga, {ctx.job_url}",
                },
            )
    except Exception:
        pass  # notification failure never blocks the agent
```

---

## 2. API submission layer

Create `src/spider_nix/intel/ats/api_submit.py`:

```python
"""
Direct API submission for ATS platforms that expose public endpoints.

Greenhouse, Lever, and Ashby all have documented submission APIs.
This avoids Playwright entirely for ~75% of remote tech job applications.

Priority:
  Tier 1 (this file): pure httpx, zero browser
  Tier 2 (browser_submit): Playwright headless, no window
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx


@dataclass
class SubmitResult:
    success: bool
    method: Literal["api", "browser", "failed"]
    message: str
    application_id: str | None = None


# ── Greenhouse ────────────────────────────────────────────────────────────────

async def greenhouse_api_submit(
    url: str,
    mapping: dict,
    cover_letter: str,
    resume_path: Path | None = None,
) -> SubmitResult:
    """
    Submit via Greenhouse Job Board API.

    POST https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}
    Content-Type: multipart/form-data

    Documented at: developers.greenhouse.io/job-board/v1
    """
    match = re.search(r'greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    if not match:
        return SubmitResult(False, "failed", "Could not parse Greenhouse URL")

    company = match.group(1)
    job_id = match.group(2)
    endpoint = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"

    # Greenhouse multipart field names
    form_data = {
        "first_name": mapping.get("first_name", ""),
        "last_name": mapping.get("last_name", ""),
        "email": mapping.get("email", ""),
        "phone": mapping.get("phone", ""),
        "location": mapping.get("location", ""),
        "resume_text": mapping.get("resume_text", ""),
        "cover_letter": cover_letter,
        "website": mapping.get("website", mapping.get("linkedin_url", "")),
    }

    # Remove empty fields
    form_data = {k: v for k, v in form_data.items() if v}

    files = {}
    if resume_path and resume_path.exists():
        files["resume"] = (resume_path.name, open(resume_path, "rb"), "application/pdf")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if files:
                resp = await client.post(endpoint, data=form_data, files=files)
            else:
                resp = await client.post(endpoint, data=form_data)

            if resp.status_code in (200, 201):
                data = resp.json()
                return SubmitResult(
                    success=True,
                    method="api",
                    message="Submitted via Greenhouse API",
                    application_id=str(data.get("id", "")),
                )
            else:
                return SubmitResult(
                    False, "failed",
                    f"Greenhouse API returned {resp.status_code}: {resp.text[:200]}"
                )
    except Exception as e:
        return SubmitResult(False, "failed", str(e))


# ── Lever ─────────────────────────────────────────────────────────────────────

async def lever_api_submit(
    url: str,
    mapping: dict,
    cover_letter: str,
    resume_path: Path | None = None,
) -> SubmitResult:
    """
    Submit via Lever Postings API.

    POST https://api.lever.co/v0/postings/{company}/{job_id}/apply
    Content-Type: multipart/form-data

    Documented at: github.com/lever/postings-api
    """
    match = re.search(r'lever\.co/([^/]+)/([a-f0-9-]{36})', url)
    if not match:
        return SubmitResult(False, "failed", "Could not parse Lever URL")

    company = match.group(1)
    job_id = match.group(2)
    endpoint = f"https://api.lever.co/v0/postings/{company}/{job_id}/apply"

    full_name = mapping.get("full_name") or (
        f"{mapping.get('first_name', '')} {mapping.get('last_name', '')}".strip()
    )

    form_data = {
        "name": full_name,
        "email": mapping.get("email", ""),
        "phone": mapping.get("phone", ""),
        "org": mapping.get("company", "voidnxlabs"),
        "urls[LinkedIn]": mapping.get("linkedin_url", ""),
        "urls[GitHub]": mapping.get("github_url", ""),
        "urls[Portfolio]": mapping.get("website", ""),
        "comments": cover_letter,
    }

    form_data = {k: v for k, v in form_data.items() if v}

    files = {}
    if resume_path and resume_path.exists():
        files["resume"] = (resume_path.name, open(resume_path, "rb"), "application/pdf")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if files:
                resp = await client.post(endpoint, data=form_data, files=files)
            else:
                resp = await client.post(endpoint, data=form_data)

            if resp.status_code in (200, 201):
                return SubmitResult(
                    success=True,
                    method="api",
                    message="Submitted via Lever API",
                )
            else:
                return SubmitResult(
                    False, "failed",
                    f"Lever API returned {resp.status_code}: {resp.text[:200]}"
                )
    except Exception as e:
        return SubmitResult(False, "failed", str(e))


# ── Ashby ─────────────────────────────────────────────────────────────────────

async def ashby_api_submit(
    url: str,
    mapping: dict,
    cover_letter: str,
    resume_path: Path | None = None,
) -> SubmitResult:
    """
    Submit via Ashby Posting API.

    POST https://api.ashbyhq.com/posting-api/application/create
    Content-Type: application/json

    Requires fetching the application form schema first to get field IDs.
    """
    match = re.search(r'ashbyhq\.com/([^/]+)/([a-f0-9-]{36})', url)
    if not match:
        return SubmitResult(False, "failed", "Could not parse Ashby URL")

    company = match.group(1)
    job_id = match.group(2)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: get form schema to find field IDs
            schema_resp = await client.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{company}/application-form",
                params={"jobPostingId": job_id},
            )
            schema_resp.raise_for_status()
            schema = schema_resp.json()

            # Step 2: map our fields to Ashby field IDs
            field_submissions = _map_ashby_fields(schema, mapping, cover_letter)

            # Step 3: submit
            payload = {
                "jobPostingId": job_id,
                "applicationForm": {"fieldSubmissions": field_submissions},
            }

            if resume_path and resume_path.exists():
                # Ashby resume upload is a separate endpoint
                with open(resume_path, "rb") as f:
                    resume_resp = await client.post(
                        "https://api.ashbyhq.com/posting-api/attachment/upload",
                        files={"file": (resume_path.name, f, "application/pdf")},
                        data={"jobPostingId": job_id},
                    )
                    if resume_resp.status_code == 200:
                        payload["applicationForm"]["resumeFileHandle"] = (
                            resume_resp.json().get("fileHandle")
                        )

            resp = await client.post(
                "https://api.ashbyhq.com/posting-api/application/create",
                json=payload,
            )

            if resp.status_code in (200, 201):
                return SubmitResult(
                    success=True,
                    method="api",
                    message="Submitted via Ashby API",
                )
            else:
                return SubmitResult(
                    False, "failed",
                    f"Ashby API returned {resp.status_code}: {resp.text[:200]}"
                )

    except Exception as e:
        return SubmitResult(False, "failed", str(e))


def _map_ashby_fields(schema: dict, mapping: dict, cover_letter: str) -> list[dict]:
    """Map profile fields to Ashby form field IDs."""
    field_submissions = []

    ASHBY_FIELD_ALIASES = {
        "name": mapping.get("full_name", f"{mapping.get('first_name','')} {mapping.get('last_name','')}".strip()),
        "email": mapping.get("email", ""),
        "phone": mapping.get("phone", ""),
        "linkedin": mapping.get("linkedin_url", ""),
        "github": mapping.get("github_url", ""),
        "website": mapping.get("website", ""),
        "coverletter": cover_letter,
        "cover_letter": cover_letter,
        "location": mapping.get("location", ""),
    }

    for field in schema.get("applicationFormDefinition", {}).get("sections", []):
        for form_field in field.get("fields", []):
            field_id = form_field.get("field", {}).get("id", "")
            label = form_field.get("field", {}).get("title", "").lower().replace(" ", "_")

            value = ASHBY_FIELD_ALIASES.get(label) or ASHBY_FIELD_ALIASES.get(
                next((k for k in ASHBY_FIELD_ALIASES if k in label), ""), ""
            )

            if value:
                field_submissions.append({"fieldId": field_id, "value": value})

    return field_submissions


# ── Browser fallback ──────────────────────────────────────────────────────────

async def browser_submit_headless(
    url: str,
    mapping: dict,
    cover_letter: str,
    resume_path: Path | None = None,
) -> SubmitResult:
    """
    Headless Playwright submission — no window, no screenshot.
    Last resort for unknown ATS (Workday, custom forms).
    """
    from playwright.async_api import async_playwright
    from ..ats.generic import fill_form
    from ...config import CrawlerConfig
    from ...browser import BrowserCrawler

    config = CrawlerConfig(use_browser=True, headless=True)
    crawler = BrowserCrawler(config=config, use_network_proxy=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=crawler.stealth.get_user_agent(),
                viewport={"width": 1440, "height": 900},
            )
            await context.add_init_script(crawler.stealth.get_playwright_stealth_script())
            page = await context.new_page()

            await page.goto(url, wait_until="networkidle")
            await fill_form(page, mapping, cover_letter)

            if resume_path and resume_path.exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(str(resume_path))
                except Exception:
                    pass

            # Find and click submit
            submit = await page.query_selector(
                "input[type='submit'], button[type='submit'], "
                "button:has-text('Submit'), button:has-text('Apply Now')"
            )
            if submit:
                await submit.click()
                await page.wait_for_timeout(3000)
                await browser.close()
                return SubmitResult(True, "browser", "Submitted via headless browser")
            else:
                await browser.close()
                return SubmitResult(False, "failed", "Submit button not found")

    except Exception as e:
        return SubmitResult(False, "failed", str(e))
```

---

## 3. Update `cli.py` — `job-apply` command

Replace the existing `job_apply` async function body entirely.
Keep the command signature identical.

```python
async def run():
    from .intel.profile import load_profile
    from .intel.personal_scorer import score_opportunity
    from .intel.llm_mapper import generate_mapping
    from .intel.approval_gate import request_approval, ApprovalContext
    from .intel.tracker import ApplicationTracker, Application
    from .intel.ats.detector import detect_from_url, ATSPlatform
    from .intel.ats.api_submit import (
        greenhouse_api_submit,
        lever_api_submit,
        ashby_api_submit,
        browser_submit_headless,
        SubmitResult,
    )
    from datetime import datetime

    # 1. Load profile
    try:
        profile = load_profile(profile_path)
        console.print(f"[green]✓[/] Profile: {profile.personal.name}")
    except FileNotFoundError as e:
        console.print(f"[red]✗ {e}[/]")
        raise typer.Exit(1)

    # 2. Detect ATS
    ats = detect_from_url(url)
    console.print(f"[cyan]ATS:[/] {ats.value}")

    # 3. Fetch job description via API (no browser)
    console.print("[cyan]Fetching job description...[/]")
    job_description = ""

    if ats == ATSPlatform.GREENHOUSE:
        from .intel.ats.greenhouse import fetch_job_description
        job_description = await fetch_job_description(url)
    elif ats == ATSPlatform.LEVER:
        from .intel.ats.lever import fetch_job_description
        job_description = await fetch_job_description(url)
    elif ats == ATSPlatform.ASHBY:
        from .intel.ats.ashby import fetch_job_description
        job_description = await fetch_job_description(url)
    else:
        # Generic: httpx scrape, no browser
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                job_description = soup.get_text(separator=" ", strip=True)[:5000]
        except Exception:
            job_description = url  # fallback: use URL as context

    # 4. Score opportunity
    from .intel.jobs import JobOpportunity
    opp = JobOpportunity(
        company=urlparse(url).netloc,
        url=url,
        title=job_description[:80],
        remote_policy="remote" if "remote" in job_description.lower() else None,
        tech_stack=[s for s in profile.primary_skills if s.lower() in job_description.lower()],
    )
    score, reasons = score_opportunity(opp, profile)

    if score == 0.0:
        console.print(f"[red]✗ Dealbreaker detected — skipping[/]")
        console.print(f"  {reasons[0]}")
        return

    console.print(f"[green]Score: {score:.0f}/100[/]  {' · '.join(reasons[:3])}")

    # 5. LLM field mapping + cover letter
    console.print("[cyan]Generating field mapping...[/]")
    mapping_result = await generate_mapping(job_description, profile)
    field_mapping = mapping_result.get("field_mapping", {})
    cover_letter = mapping_result.get("cover_letter", profile.cover_letter_template)

    # 6. TUI approval gate (ntfy fires in background if NTFY_TOKEN set)
    company = field_mapping.get("company") or urlparse(url).netloc
    role = job_description[:80].split("\n")[0].strip()

    ctx = ApprovalContext(
        job_url=url,
        company=company,
        role=role,
        ats_platform=ats.value,
        score=score,
        score_reasons=reasons,
        field_mapping=field_mapping,
        cover_letter=cover_letter,
        salary_expectation=str(profile.preferences.min_salary_usd),
    )

    if dry_run:
        # Show TUI but replace submit with display-only
        console.print("\n[yellow]── DRY RUN ── form will not be submitted[/]\n")
        from rich.panel import Panel
        from rich.table import Table
        table = Table(show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        for k, v in field_mapping.items():
            table.add_row(k, str(v)[:80])
        console.print(table)
        console.print(Panel(cover_letter[:400] + "...", title="Cover Letter"))
        return

    approved, final_mapping = await request_approval(ctx)

    if not approved:
        console.print("[yellow]⊘ Skipped[/]")
        return

    # 7. Submit — API first, browser headless as fallback
    console.print("[cyan]Submitting...[/]")
    result: SubmitResult

    if ats == ATSPlatform.GREENHOUSE:
        result = await greenhouse_api_submit(url, final_mapping, cover_letter, resume)
    elif ats == ATSPlatform.LEVER:
        result = await lever_api_submit(url, final_mapping, cover_letter, resume)
    elif ats == ATSPlatform.ASHBY:
        result = await ashby_api_submit(url, final_mapping, cover_letter, resume)
    else:
        result = await browser_submit_headless(url, final_mapping, cover_letter, resume)

    if not result.success:
        console.print(f"[red]✗ Submission failed: {result.message}[/]")
        retry = Confirm.ask("Try browser fallback?", default=True)
        if retry:
            result = await browser_submit_headless(url, final_mapping, cover_letter, resume)

    if result.success:
        console.print(f"[bold green]✅ {result.message}[/]")
    else:
        console.print(f"[red]✗ All methods failed: {result.message}[/]")
        return

    # 8. Track
    app = Application(
        url=url,
        company=company,
        role=role,
        ats_platform=ats.value,
        status="submitted",
        applied_at=datetime.now(),
        cover_letter=cover_letter,
    )
    tracker = ApplicationTracker()
    await tracker.record_application(app)
    console.print("[dim]✓ Logged to applications.db[/]")
```

---

## 4. Tests to add

Append to `tests/test_job_agent.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from spider_nix.intel.ats.api_submit import (
    greenhouse_api_submit, lever_api_submit, SubmitResult
)
from spider_nix.intel.approval_gate import ApprovalContext, _tui_approval


@pytest.mark.asyncio
async def test_greenhouse_api_submit_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "123456"}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await greenhouse_api_submit(
            url="https://boards.greenhouse.io/acme/jobs/123456",
            mapping={"first_name": "Bello", "last_name": "Pina", "email": "test@test.com"},
            cover_letter="Test cover letter.",
        )
    assert result.success is True
    assert result.method == "api"
    assert result.application_id == "123456"


@pytest.mark.asyncio
async def test_greenhouse_bad_url():
    result = await greenhouse_api_submit(
        url="https://careers.example.com/jobs/123",
        mapping={},
        cover_letter="",
    )
    assert result.success is False
    assert "parse" in result.message.lower()


@pytest.mark.asyncio
async def test_lever_api_submit_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await lever_api_submit(
            url="https://jobs.lever.co/acme/550e8400-e29b-41d4-a716-446655440000",
            mapping={"first_name": "Bello", "last_name": "Pina", "email": "test@test.com"},
            cover_letter="Test.",
        )
    assert result.success is True


def test_approval_context_fields(mock_profile):
    ctx = ApprovalContext(
        job_url="https://example.com",
        company="Acme",
        role="Security Architect",
        ats_platform="greenhouse",
        score=94.0,
        score_reasons=["Remote ✓", "Rust ✓"],
        field_mapping={"first_name": "Bello", "email": "test@test.com"},
        cover_letter="Cover letter text.",
    )
    assert ctx.score == 94.0
    assert len(ctx.score_reasons) == 2
    assert ctx.ats_platform == "greenhouse"
```

---

## 5. Environment variables — update `.env.example`

```bash
# ntfy self-hosted (your own Brazilian IP — no intermediary)
# Leave NTFY_TOKEN unset to disable push notifications entirely
NTFY_URL=https://push.voidnx.com
NTFY_TOPIC=job-agent
NTFY_TOKEN=tk_xxxxxxxxxxxx

# Profile
SPIDER_PROFILE=./profile.toml

# LLM (local ml-ops-api)
LLM_API_URL=http://localhost:9000
LLM_MODEL=mistral
```

---

## Implementation order

Execute in this order — each step is independently testable:

```
1. src/spider_nix/intel/ats/api_submit.py     — pure httpx, no side effects
2. tests/test_job_agent.py additions          — test api_submit in isolation
3. src/spider_nix/intel/approval_gate.py      — rewrite, TUI + ntfy
4. cli.py job-apply body                      — wire everything together
5. manual test: spider job-apply <gh_url> --dry-run
6. manual test: spider job-apply <lever_url> --dry-run
```

---

## Usage

```bash
# Dry run — shows TUI diff, never submits
spider job-apply https://boards.greenhouse.io/cloudflare/jobs/123456 --dry-run

# Real run — TUI approval, API submission
spider job-apply https://boards.greenhouse.io/cloudflare/jobs/123456 \
  --resume ~/resume.pdf

# With ntfy on your server (notification only, not required for approval)
export NTFY_URL=https://push.voidnx.com
export NTFY_TOKEN=tk_xxxxxxxxxxxx
spider job-apply https://jobs.lever.co/stripe/abc-123 --resume ~/resume.pdf

# History
spider job-history
spider job-history --status submitted
```

---

## What changed from Phase 1

```
REMOVED:  entire Telegram dependency
REMOVED:  screenshot-based approval
REMOVED:  browser window for approval review
REMOVED:  polling loop for callback

ADDED:    Rich TUI interactive diff with edit capability
ADDED:    API-first submission (Greenhouse/Lever/Ashby)
ADDED:    ntfy fire-and-forget (non-blocking, optional)
ADDED:    SubmitResult dataclass with method tracking
ADDED:    browser_submit_headless as explicit last resort
ADDED:    retry prompt if API submission fails
```
