"""
Ashby ATS adapter.

Ashby exposes a public API:
  GET https://api.ashbyhq.com/posting-api/job-board/{company}/published
  GET https://api.ashbyhq.com/posting-api/job-board/{company}/application-form?jobPostingId={id}

Application form is at jobs.ashbyhq.com/{company}/{job_id}
"""

import re
import httpx
from playwright.async_api import Page


async def fetch_job_description(url: str) -> str:
    """Fetch job description via Ashby public API."""
    match = re.search(r"ashbyhq\.com/([^/]+)/([^/?]+)", url)
    if not match:
        return ""

    company = match.group(1)
    job_id = match.group(2)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{company}/published"
            )
            resp.raise_for_status()
            data = resp.json()

            postings = data.get("jobPostings", [])
            for posting in postings:
                if posting.get("id") == job_id or posting.get("externalLink", "").endswith(job_id):
                    title = posting.get("title", "")
                    desc = posting.get("descriptionPlain", "") or re.sub(
                        r"<[^>]+>", " ", posting.get("descriptionHtml", "")
                    )
                    return f"{title}\n\n{desc}"
    except Exception:
        pass

    return ""


ASHBY_SELECTORS = {
    "first_name": "input[name='_systemfield_name'], input[placeholder*='First'], input[id*='firstName']",
    "last_name": "input[placeholder*='Last'], input[id*='lastName']",
    "email": "input[type='email'], input[name='_systemfield_email']",
    "phone": "input[type='tel'], input[name='_systemfield_phone']",
    "linkedin": "input[placeholder*='LinkedIn'], input[name*='linkedin']",
    "github": "input[placeholder*='GitHub'], input[name*='github']",
    "website": "input[placeholder*='Website'], input[placeholder*='Portfolio']",
    "cover_letter_text": "textarea[name*='cover'], textarea[placeholder*='cover']",
    "submit": "button[type='submit']",
}


async def fill_form(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """Fill Ashby application form."""
    full_mapping = {**field_mapping, "cover_letter_text": cover_letter}

    for field_key, selector in ASHBY_SELECTORS.items():
        if field_key == "submit":
            continue

        value = full_mapping.get(field_key)
        if not value:
            continue

        try:
            element = await page.query_selector(selector)
            if element:
                input_type = await element.get_attribute("type")
                if input_type == "file":
                    continue
                await element.click()
                await element.fill(str(value))
        except Exception:
            continue

    return True
