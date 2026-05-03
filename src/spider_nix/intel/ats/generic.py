"""
Generic ATS adapter using FormAnalyzer + LLM field mapping.

Used when ATS is unknown. Extracts all form fields via FormAnalyzer,
sends them to LLM to map against profile, then fills via Playwright
using human behavioral simulation to avoid bot detection.
"""

import asyncio
import logging

from playwright.async_api import Page

from ...osint.web_discovery import FormAnalyzer
from ..human_behavior import human_move_to, human_type
from ..llm_mapper import generate_mapping
from ..profile import Profile

logger = logging.getLogger(__name__)


async def fetch_job_description(page: Page) -> str:
    """Extract job description from current page via text content."""
    try:
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
    Fill a generic form with human behavioral simulation.

    Timeout layers:
      - 30 s  form field discovery
      - 60 s  total form filling (all fields)
      -  5 s  per individual field
    """
    try:
        async with asyncio.timeout(30):
            fields = await _discover_fields(page)
    except TimeoutError:
        logger.warning("generic.fill_form: field discovery timed out")
        return False

    full_mapping = {**field_mapping, "cover_letter": cover_letter}

    try:
        async with asyncio.timeout(60):
            await _fill_fields(page, fields, full_mapping)
    except TimeoutError:
        logger.warning("generic.fill_form: filling timed out after 60 s (partial fill)")

    return True


async def _discover_fields(page: Page) -> list[dict]:
    return await page.evaluate("""
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


async def _fill_fields(page: Page, fields: list[dict], mapping: dict) -> None:
    for field in fields:
        search_key = " ".join([
            field.get("name", ""),
            field.get("id", ""),
            field.get("placeholder", ""),
            field.get("label", ""),
        ]).lower()

        value = _fuzzy_match(search_key, mapping)
        if not value:
            continue

        selector = field["selector"]

        try:
            async with asyncio.timeout(5):
                el = await page.query_selector(selector)
                if el is None:
                    continue

                # Move mouse to field before interacting (Layer 3: mouse trajectory)
                await human_move_to(page, el, overshoot=False)

                field_type = field.get("type", "text")
                if field_type == "checkbox":
                    if str(value).lower() in ("true", "yes", "1"):
                        await el.check()
                elif field_type in ("radio", "select-one"):
                    await el.click()
                elif field.get("tag") == "TEXTAREA" or field_type == "text":
                    await el.click()
                    await el.select_text()
                    # Human typing (Layer 3: keystroke dynamics)
                    await human_type(page, selector, str(value))
                else:
                    await el.fill(str(value))

        except TimeoutError:
            logger.debug("Field fill timed out: %s", selector)
        except Exception as exc:
            logger.debug("Field fill error (%s): %s", selector, exc)


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
