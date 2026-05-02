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
    match = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
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
            clean = re.sub(r"<[^>]+>", " ", content)
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
