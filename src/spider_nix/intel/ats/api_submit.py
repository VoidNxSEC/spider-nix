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
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if not match:
        return SubmitResult(False, "failed", "Could not parse Greenhouse URL")

    company = match.group(1)
    job_id = match.group(2)
    endpoint = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}"

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
                    False,
                    "failed",
                    f"Greenhouse API returned {resp.status_code}: {resp.text[:200]}",
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
    match = re.search(r"lever\.co/([^/]+)/([a-f0-9-]{36})", url)
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
                    False,
                    "failed",
                    f"Lever API returned {resp.status_code}: {resp.text[:200]}",
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
    match = re.search(r"ashbyhq\.com/([^/]+)/([a-f0-9-]{36})", url)
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
            payload: dict = {
                "jobPostingId": job_id,
                "applicationForm": {"fieldSubmissions": field_submissions},
            }

            if resume_path and resume_path.exists():
                with open(resume_path, "rb") as f:
                    resume_resp = await client.post(
                        "https://api.ashbyhq.com/posting-api/attachment/upload",
                        files={"file": (resume_path.name, f, "application/pdf")},
                        data={"jobPostingId": job_id},
                    )
                    if resume_resp.status_code == 200:
                        payload["applicationForm"]["resumeFileHandle"] = resume_resp.json().get(
                            "fileHandle"
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
                    False,
                    "failed",
                    f"Ashby API returned {resp.status_code}: {resp.text[:200]}",
                )

    except Exception as e:
        return SubmitResult(False, "failed", str(e))


def _map_ashby_fields(schema: dict, mapping: dict, cover_letter: str) -> list[dict]:
    """Map profile fields to Ashby form field IDs."""
    field_submissions = []

    ASHBY_FIELD_ALIASES: dict[str, str] = {
        "name": mapping.get(
            "full_name", f"{mapping.get('first_name', '')} {mapping.get('last_name', '')}".strip()
        ),
        "email": mapping.get("email", ""),
        "phone": mapping.get("phone", ""),
        "linkedin": mapping.get("linkedin_url", ""),
        "github": mapping.get("github_url", ""),
        "website": mapping.get("website", ""),
        "coverletter": cover_letter,
        "cover_letter": cover_letter,
        "location": mapping.get("location", ""),
    }

    for section in schema.get("applicationFormDefinition", {}).get("sections", []):
        for form_field in section.get("fields", []):
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
    from .generic import fill_form
    from ...config import CrawlerConfig
    from ...browser import BrowserCrawler

    config = CrawlerConfig(use_browser=True, headless=True)
    crawler = BrowserCrawler(config=config, use_network_proxy=True)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Fresh fingerprint per call — identical viewport every time is a bot signal
            fp = crawler.stealth.get_fingerprint()
            context = await browser.new_context(
                user_agent=crawler.stealth.get_user_agent(),
                viewport={"width": fp["screen"]["width"], "height": fp["screen"]["height"]},
                locale=fp["language"],
                timezone_id=fp["timezone"],
                ignore_https_errors=True,
            )
            await context.add_init_script(crawler.stealth.get_playwright_stealth_script())
            page = await context.new_page()
            # 150 ms settle — closes stealth injection race on first navigation
            await page.wait_for_timeout(150)

            # domcontentloaded + explicit timeout — networkidle hangs on long-polling pages
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await fill_form(page, mapping, cover_letter)

            if resume_path and resume_path.exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(str(resume_path))
                except Exception:
                    pass

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
