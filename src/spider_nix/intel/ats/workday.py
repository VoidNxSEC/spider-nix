"""Workday ATS adapter — best effort, requires browser rendering."""

from playwright.async_api import Page
from .generic import fetch_job_description, fill_form  # reuse generic

# Workday-specific data-automation-id selectors
WORKDAY_EXTRA_SELECTORS = {
    "legalName": "input[data-automation-id='legalNameSection_firstName']",
    "lastName": "input[data-automation-id='legalNameSection_lastName']",
    "email": "input[data-automation-id='email']",
    "phone": "input[data-automation-id='phone']",
    "coverLetter": "textarea[data-automation-id='coverLetter']",
}


async def fill_form_workday(page: Page, field_mapping: dict, cover_letter: str) -> bool:
    """Try Workday-specific selectors, then fall back to generic."""
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

    await fill_form(page, field_mapping, cover_letter)
    return True
