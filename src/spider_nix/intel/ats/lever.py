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
    match = re.search(r"lever\.co/([^/]+)/([a-f0-9-]{36})", url)
    if not match:
        return ""

    company = match.group(1)
    job_id = match.group(2)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"https://api.lever.co/v0/postings/{company}/{job_id}")
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
    "first_name": "input[name='name']",  # Lever uses full name
    "email": "input[name='email']",
    "phone": "input[name='phone']",
    "org": "input[name='org']",  # Current company
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
        "first_name": field_mapping.get("full_name")
        or (f"{field_mapping.get('first_name', '')} {field_mapping.get('last_name', '')}".strip()),
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
