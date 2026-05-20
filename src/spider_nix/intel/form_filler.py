"""
Form Auto-Filler — smart form filling for job applications and web forms.

Builds on FormAnalyzer to automatically match profile data to form fields
using heuristic field-name matching. Generates fill data ready for submission.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spider_nix.osint.web_discovery import FormAnalysis, FormAnalyzer, FormField

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User data profile for autofill
# ---------------------------------------------------------------------------


@dataclass
class AutoFillProfile:
    """Personal/profile data used to fill forms automatically."""

    # Basic info
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    postal_code: str = ""

    # Professional
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    website: str = ""
    twitter_url: str = ""

    # Resume
    resume_path: str = ""
    cover_letter_text: str = ""

    # Job preferences
    salary_expectation: str = ""
    available_start_date: str = ""
    work_authorization: str = ""  # e.g. "US Citizen", "EU Work Permit"
    requires_sponsorship: str = ""

    # Demographics (often EEO questions)
    gender: str = ""
    ethnicity: str = ""
    veteran_status: str = ""
    disability_status: str = ""

    # Education
    highest_education: str = ""  # "Bachelor's", "Master's", etc.
    university: str = ""
    degree: str = ""
    graduation_year: str = ""

    # Experience
    years_experience: str = ""
    current_company: str = ""
    current_title: str = ""

    # Custom overrides
    custom_fields: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> AutoFillProfile:
        """Load profile from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, str]:
        """Convert to flat dict for serialization."""
        result = {}
        for field_name in self.__dataclass_fields__:
            if field_name == "custom_fields":
                continue
            val = getattr(self, field_name)
            if val:
                result[field_name] = val
        result.update(self.custom_fields)
        return result


# ---------------------------------------------------------------------------
# Field-to-profile matching
# ---------------------------------------------------------------------------


class FieldMatcher:
    """
    Heuristic matching of form field names to profile fields.

    Uses keyword-based rules to guess which profile field
    corresponds to each form field.
    """

    # Mapping: form field keywords → profile attribute
    FIELD_MAP: list[tuple[list[str], str]] = [
        # Name fields
        (
            ["first_name", "firstname", "givenname", "fname", "first-name", "firstName"],
            "first_name",
        ),
        (
            ["last_name", "lastname", "surname", "familyname", "lname", "last-name", "lastName"],
            "last_name",
        ),
        (
            ["full_name", "fullname", "name", "your_name", "your-name", "full-name", "custname"],
            "full_name",
        ),
        # Contact
        (["email", "e-mail", "emailaddress", "email_address", "user_email"], "email"),
        (
            [
                "phone",
                "telephone",
                "mobile",
                "cell",
                "contact_number",
                "phonenumber",
                "custtel",
                "tel",
                "telefone",
            ],
            "phone",
        ),
        # Location
        (["city", "town", "municipality"], "city"),
        (["state", "province", "region"], "state"),
        (["country", "nation", "country_of_residence"], "country"),
        (["postal", "zip", "zipcode", "zip_code", "postcode", "postalcode"], "postal_code"),
        (["location", "address", "current_location"], "location"),
        # Professional links
        (["linkedin", "linkedin_url", "linkedinurl", "linkedin_profile"], "linkedin_url"),
        (["github", "github_url", "githuburl", "github_username"], "github_url"),
        (["portfolio", "portfolio_url", "portfoliourl", "personal_website"], "portfolio_url"),
        (["website", "website_url", "web_site", "blog"], "website"),
        (["twitter", "twitter_url", "x.com", "x_profile"], "twitter_url"),
        # Resume / CV
        (["resume", "cv", "resume_upload", "upload_resume", "attach_resume"], "resume_path"),
        (
            ["cover_letter", "coverletter", "cover", "message", "why_do_you", "why are you"],
            "cover_letter_text",
        ),
        # Job preferences
        (
            ["salary", "salary_expectation", "desired_salary", "compensation", "expected_pay"],
            "salary_expectation",
        ),
        (
            ["start_date", "available", "availability", "earliest_start", "startdate"],
            "available_start_date",
        ),
        (
            [
                "work_authorization",
                "authorized",
                "eligible_to_work",
                "legally_authorized",
                "right_to_work",
            ],
            "work_authorization",
        ),
        (
            ["sponsor", "sponsorship", "visa_sponsor", "require_sponsor", "need_sponsor"],
            "requires_sponsorship",
        ),
        # Education
        (
            ["education", "highest_education", "education_level", "degree_level"],
            "highest_education",
        ),
        (["university", "school", "college", "institution"], "university"),
        (["degree", "major", "field_of_study"], "degree"),
        (["graduation", "grad_year", "graduation_year", "year_of_graduation"], "graduation_year"),
        # Experience
        (
            [
                "years_experience",
                "experience_years",
                "total_experience",
                "yoe",
                "years_of_experience",
            ],
            "years_experience",
        ),
        (["current_company", "current_employer", "employer"], "current_company"),
        (["current_title", "current_role", "current_position", "job_title"], "current_title"),
        # Demographics (EEO)
        (["gender", "sex", "gender_identity"], "gender"),
        (["ethnicity", "race", "ethnic_background"], "ethnicity"),
        (["veteran", "veteran_status", "military"], "veteran_status"),
        (["disability", "disabled", "disability_status"], "disability_status"),
    ]

    def match(self, form_field: FormField) -> str | None:
        """
        Match a form field to a profile attribute.

        Returns the profile attribute name, or None if no match.
        """
        field_name = form_field.name.lower().strip()
        field_placeholder = (form_field.placeholder or "").lower().strip()

        combined = f"{field_name} {field_placeholder}"

        # First try custom fields
        # (handled by caller)

        # Try keyword matching
        best_match = None
        best_score = 0

        for keywords, profile_attr in self.FIELD_MAP:
            for kw in keywords:
                if kw in combined:
                    # Longer keyword match = better
                    score = len(kw)
                    if score > best_score:
                        best_score = score
                        best_match = profile_attr
                    break  # Found a match in this group

        return best_match


# ---------------------------------------------------------------------------
# Auto-Filler
# ---------------------------------------------------------------------------


class FormAutoFiller:
    """
    Automatically fill web forms using a user profile.

    Analyzes forms, matches fields to profile data,
    and generates filled form payloads or Playwright scripts.
    """

    def __init__(self, profile: AutoFillProfile):
        self.profile = profile
        self.analyzer = FormAnalyzer()
        self.matcher = FieldMatcher()

    async def analyze_and_fill(self, url: str, html: str) -> list[dict[str, Any]]:
        """
        Analyze all forms on a page and generate fill data.

        Returns:
            List of dicts with form info + fill data
        """
        forms = await self.analyzer.analyze_page(url, html)
        results = []

        for form in forms:
            fill_data = self._generate_fill_data(form)
            results.append(
                {
                    "form_url": form.url,
                    "form_action": form.action,
                    "form_method": form.method,
                    "form_purpose": form.purpose,
                    "fields_count": form.field_count,
                    "has_captcha": form.has_captcha,
                    "has_file_upload": form.has_file_upload,
                    "fill_data": fill_data,
                    "unmatched_fields": [
                        f.name
                        for f in form.fields
                        if f.name not in fill_data
                        and f.field_type not in ("submit", "button", "reset", "hidden")
                    ],
                    "fill_coverage": len(fill_data) / max(form.field_count, 1),
                }
            )

        return results

    def _generate_fill_data(self, form: FormAnalysis) -> dict[str, str]:
        """Generate field_name → value mapping for a form."""
        fill: dict[str, str] = {}

        for field in form.fields:
            value = self._value_for_field(field)
            if value is not None:
                fill[field.name] = value

        return fill

    def _value_for_field(self, field: FormField) -> str | None:
        """Determine the value for a single form field."""
        fname = field.name.lower().strip()
        ftype = field.field_type.lower()

        # Check custom overrides first
        if field.name in self.profile.custom_fields:
            return self.profile.custom_fields[field.name]

        # If field has predefined options (select), try to match one
        if ftype == "select" and field.options:
            return self._match_select_option(field)

        # Try keyword matching
        profile_attr = self.matcher.match(field)
        if profile_attr:
            value = getattr(self.profile, profile_attr, None)
            if value:
                return str(value)

        # Type-based defaults
        if ftype in ("submit", "button", "reset", "hidden", "image"):
            return None

        if ftype == "email" and self.profile.email:
            return self.profile.email
        if ftype == "tel" and self.profile.phone:
            return self.profile.phone
        if ftype == "url" and self.profile.website:
            return self.profile.website

        # Check by common name patterns not in FIELD_MAP
        if "first" in fname and self.profile.first_name:
            return self.profile.first_name
        if "last" in fname and self.profile.last_name:
            return self.profile.last_name
        if "name" in fname and self.profile.full_name:
            return self.profile.full_name

        return None

    def _match_select_option(self, field: FormField) -> str | None:
        """Try to match a select field option to profile data."""
        profile_attr = self.matcher.match(field)
        if not profile_attr:
            return None

        profile_value = str(getattr(self.profile, profile_attr, "")).lower()
        if not profile_value:
            return None

        # Try exact match
        for option in field.options:
            if option.lower().strip() == profile_value:
                return option

        # Try partial match
        for option in field.options:
            if profile_value in option.lower() or option.lower() in profile_value:
                return option

        # For yes/no questions
        if profile_value in ("yes", "true", "1"):
            for option in field.options:
                if option.lower().strip() in ("yes", "true", "1"):
                    return option
        elif profile_value in ("no", "false", "0"):
            for option in field.options:
                if option.lower().strip() in ("no", "false", "0"):
                    return option

        return None

    # ---- Script generation ----

    def generate_playwright_script(self, url: str, fill_results: list[dict]) -> str:
        """
        Generate a Playwright Python script that fills and submits the forms.

        Returns:
            Python script as a string
        """
        lines = [
            '"""Auto-generated Playwright script for form filling."""',
            "import asyncio",
            "from playwright.async_api import async_playwright",
            "",
            "",
            "async def fill_forms():",
            "    async with async_playwright() as p:",
            "        browser = await p.chromium.launch(headless=False)",
            "        page = await browser.new_page()",
            f"        await page.goto('{url}')",
            "        await page.wait_for_load_state('networkidle')",
            "",
        ]

        for i, result in enumerate(fill_results):
            fill_data = result.get("fill_data", {})
            if not fill_data:
                continue

            lines.append(f"        # Form {i + 1}: {result.get('form_purpose', 'unknown')}")
            lines.append(f"        # Action: {result.get('form_action', 'N/A')}")

            for field_name, value in fill_data.items():
                escaped_value = value.replace("'", "\\'").replace("\n", "\\n")
                lines.append(
                    f"        await page.fill('[name=\"{field_name}\"]', '{escaped_value}')"
                )

            lines.append("        # Uncomment to submit:")
            lines.append(f"        # await page.click('[type=\"submit\"]')")
            lines.append("")

        lines.extend(
            [
                "        # Keep browser open for review",
                "        await asyncio.sleep(30)",
                "        await browser.close()",
                "",
                "",
                "asyncio.run(fill_forms())",
            ]
        )

        return "\n".join(lines)

    def generate_curl_commands(self, fill_results: list[dict]) -> str:
        """
        Generate curl commands for direct HTTP form submission.

        Returns:
            Shell script as a string
        """
        lines = ["#!/bin/bash", "# Auto-generated curl commands for form submission", ""]

        for i, result in enumerate(fill_results):
            fill_data = result.get("fill_data", {})
            if not fill_data:
                continue

            action = result.get("form_action", "")
            method = result.get("form_method", "post").upper()

            lines.append(f"# Form {i + 1}: {result.get('form_purpose', 'unknown')}")

            if method == "GET":
                params = "&".join(f"{k}={v}" for k, v in fill_data.items())
                lines.append(f"curl -X GET '{action}?{params}'")
            else:
                data_args = " ".join(f"-F '{k}={v}'" for k, v in fill_data.items())
                lines.append(f"curl -X {method} '{action}' {data_args}")

            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


async def autofill_url(
    url: str,
    profile: AutoFillProfile | str | Path,
    html: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch a URL, analyze its forms, and generate fill data.

    Args:
        url: Page URL to analyze
        profile: AutoFillProfile instance or path to JSON profile
        html: Optional pre-fetched HTML (avoids extra request)

    Returns:
        List of fill results per form
    """
    if isinstance(profile, (str, Path)):
        profile = AutoFillProfile.from_json(profile)

    if html is None:
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text

    filler = FormAutoFiller(profile)
    return await filler.analyze_and_fill(url, html)
