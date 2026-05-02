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
        search_key = " ".join(
            [
                field.get("name", ""),
                field.get("id", ""),
                field.get("placeholder", ""),
                field.get("label", ""),
            ]
        ).lower()

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
