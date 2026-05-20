"""
Form Auto-Filler — smart form filling for job applications and web forms.

Builds on FormAnalyzer to automatically match profile data to form fields
using heuristic field-name matching with confidence scores. Supports
ATS-specific field templates for higher accuracy on Greenhouse, Lever, etc.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spider_nix.intel.template_loader import detect_platform_from_url, load_template
from spider_nix.osint.web_discovery import FormAnalysis, FormAnalyzer, FormField

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ATS Platform Detection
# ---------------------------------------------------------------------------


def detect_ats_platform(url: str, html: str | None = None) -> str | None:
    """
    Detect which ATS platform a URL belongs to.

    Uses external YAML templates first, then falls back to built-in patterns.
    """
    # Try external templates
    platform = detect_platform_from_url(url)
    if platform:
        return platform

    # Fallback to built-in detection
    url_lower = url.lower()
    checks: list[tuple[str, list[str]]] = [
        ("greenhouse", ["boards.greenhouse.io"]),
        ("lever", ["jobs.lever.co"]),
        ("ashby", ["jobs.ashbyhq.com"]),
        ("workday", ["myworkdayjobs.com"]),
        ("bamboohr", ["bamboohr.com"]),
        ("smartrecruiters", ["smartrecruiters.com"]),
    ]
    for p, patterns in checks:
        for pat in patterns:
            if pat in url_lower:
                return p
    return None


# ---------------------------------------------------------------------------
# ATS-Specific Field Templates
# ---------------------------------------------------------------------------

# Each template maps a profile attribute to a list of possible field names
# used by that ATS. Fields are ordered by specificity (best match first).

ATS_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "greenhouse": {
        "first_name": ["first_name", "firstName", "firstname", "candidate_first_name"],
        "last_name": ["last_name", "lastName", "lastname", "candidate_last_name"],
        "full_name": ["full_name", "fullName", "name", "fullname"],
        "email": ["email", "candidate_email", "email_address", "candidateEmail"],
        "phone": ["phone", "phone_number", "candidate_phone", "phoneNumber"],
        "location": ["location", "candidate_location", "city"],
        "linkedin_url": ["linkedin_url", "url_linkedin", "linkedin", "linkedinUrl"],
        "github_url": ["github_url", "url_github", "github", "githubUrl"],
        "portfolio_url": ["portfolio_url", "url_portfolio", "website", "portfolioUrl"],
        "resume_path": ["resume", "resume_upload", "attachments[0]", "upload_resume"],
        "cover_letter_text": ["cover_letter", "cover_letter_text", "coverLetter", "message"],
        "salary_expectation": ["salary_expectation", "desired_salary", "desiredSalary"],
        "work_authorization": ["work_authorization", "authorized_to_work", "eligible_to_work"],
        "requires_sponsorship": ["requires_sponsorship", "visa_sponsorship", "need_sponsor"],
        "gender": ["gender", "gender_identity", "eeo_gender"],
        "ethnicity": ["ethnicity", "race", "eeo_ethnicity", "hispanic_latino"],
        "veteran_status": ["veteran_status", "veteran", "protected_veteran"],
        "disability_status": ["disability_status", "disability", "disabled"],
    },
    "lever": {
        "full_name": ["name", "fullName", "full_name"],
        "first_name": ["first_name", "firstName"],
        "last_name": ["last_name", "lastName"],
        "email": ["email", "candidateEmail", "email_address"],
        "phone": ["phone", "phoneNumber", "phone_number"],
        "location": ["location", "region"],
        "linkedin_url": ["linkedin", "linkedinUrl", "url_linkedin"],
        "github_url": ["github", "githubUrl", "url_github"],
        "portfolio_url": ["portfolio", "portfolioUrl", "website"],
        "resume_path": ["resume", "cv", "resumeUpload"],
        "cover_letter_text": ["coverLetter", "cover_letter", "additionalInformation"],
        "salary_expectation": ["salaryExpectation", "desiredSalary", "salary"],
        "work_authorization": ["workAuthorization", "eligibleToWork"],
        "requires_sponsorship": ["requiresSponsorship", "visaSponsorship"],
        "gender": ["gender", "eeo_gender"],
        "ethnicity": ["ethnicity", "eeo_ethnicity", "race"],
        "veteran_status": ["veteran", "veteranStatus", "protectedVeteran"],
        "disability_status": ["disability", "disabilityStatus"],
        "years_experience": ["yearsOfExperience", "years_experience", "experience"],
        "current_company": ["currentCompany", "current_company", "mostRecentEmployer"],
        "current_title": ["currentTitle", "current_title", "mostRecentTitle"],
        "highest_education": ["education", "highestDegree", "educationLevel"],
        "university": ["school", "university", "college"],
        "degree": ["degree", "major", "fieldOfStudy"],
    },
    "ashby": {
        "first_name": ["firstName", "first_name", "givenName"],
        "last_name": ["lastName", "last_name", "familyName"],
        "full_name": ["fullName", "full_name", "name"],
        "email": ["email", "emailAddress", "candidateEmail"],
        "phone": ["phone", "phoneNumber", "mobilePhone"],
        "location": ["location", "city", "region"],
        "linkedin_url": ["linkedin", "linkedinUrl", "linkedinProfile"],
        "github_url": ["github", "githubUrl", "githubProfile"],
        "resume_path": ["resume", "cv", "resumeFile"],
        "cover_letter_text": ["coverLetter", "coverLetterText", "message"],
        "salary_expectation": ["salaryExpectation", "desiredSalary"],
        "work_authorization": ["workAuthorization", "authorizedToWork"],
        "requires_sponsorship": ["requiresSponsorship", "visaSponsorship"],
    },
    "workday": {
        "first_name": ["legalFirstName", "firstName", "first_name"],
        "last_name": ["legalLastName", "lastName", "last_name"],
        "email": ["email", "primaryEmail", "emailAddress"],
        "phone": ["phone", "primaryPhone", "phoneNumber"],
        "location": ["city", "location", "address"],
    },
}

# Generic fallback — used when no ATS template matches
GENERIC_FIELD_MAP: dict[str, list[str]] = {
    "first_name": [
        "first_name",
        "firstname",
        "givenname",
        "fname",
        "first-name",
        "firstName",
        "first",
    ],
    "last_name": [
        "last_name",
        "lastname",
        "surname",
        "familyname",
        "lname",
        "last-name",
        "lastName",
        "last",
    ],
    "full_name": [
        "full_name",
        "fullname",
        "name",
        "your_name",
        "your-name",
        "full-name",
        "custname",
        "candidatename",
    ],
    "email": [
        "email",
        "e-mail",
        "emailaddress",
        "email_address",
        "user_email",
        "custemail",
        "candidateEmail",
    ],
    "phone": [
        "phone",
        "telephone",
        "mobile",
        "cell",
        "contact_number",
        "phonenumber",
        "custtel",
        "tel",
        "telefone",
        "phoneNumber",
    ],
    "location": ["location", "address", "current_location", "city_state"],
    "city": ["city", "town", "municipality"],
    "state": ["state", "province", "region"],
    "country": ["country", "nation", "country_of_residence"],
    "postal_code": ["postal", "zip", "zipcode", "zip_code", "postcode", "postalcode"],
    "linkedin_url": ["linkedin", "linkedin_url", "linkedinurl", "linkedin_profile", "linkedinUrl"],
    "github_url": ["github", "github_url", "githuburl", "github_username", "githubUrl"],
    "portfolio_url": [
        "portfolio",
        "portfolio_url",
        "portfoliourl",
        "personal_website",
        "website_url",
    ],
    "website": ["website", "website_url", "web_site", "blog", "homepage"],
    "twitter_url": ["twitter", "twitter_url", "x.com", "x_profile"],
    "resume_path": [
        "resume",
        "cv",
        "resume_upload",
        "upload_resume",
        "attach_resume",
        "resumeFile",
    ],
    "cover_letter_text": [
        "cover_letter",
        "coverletter",
        "cover",
        "message",
        "why_do_you",
        "why are you",
        "coverLetter",
    ],
    "salary_expectation": [
        "salary",
        "salary_expectation",
        "desired_salary",
        "compensation",
        "expected_pay",
        "desiredSalary",
    ],
    "available_start_date": [
        "start_date",
        "available",
        "availability",
        "earliest_start",
        "startdate",
    ],
    "work_authorization": [
        "work_authorization",
        "authorized",
        "eligible_to_work",
        "legally_authorized",
        "right_to_work",
        "workAuth",
    ],
    "requires_sponsorship": [
        "sponsor",
        "sponsorship",
        "visa_sponsor",
        "require_sponsor",
        "need_sponsor",
        "visaSponsorship",
    ],
    "highest_education": [
        "education",
        "highest_education",
        "education_level",
        "degree_level",
        "educationLevel",
    ],
    "university": ["university", "school", "college", "institution"],
    "degree": ["degree", "major", "field_of_study", "fieldOfStudy"],
    "graduation_year": ["graduation", "grad_year", "graduation_year", "year_of_graduation"],
    "years_experience": [
        "years_experience",
        "experience_years",
        "total_experience",
        "yoe",
        "years_of_experience",
        "yearsExperience",
    ],
    "current_company": ["current_company", "current_employer", "employer", "currentCompany"],
    "current_title": [
        "current_title",
        "current_role",
        "current_position",
        "job_title",
        "currentTitle",
    ],
    "gender": ["gender", "sex", "gender_identity", "eeo_gender"],
    "ethnicity": ["ethnicity", "race", "ethnic_background", "eeo_ethnicity"],
    "veteran_status": ["veteran", "veteran_status", "military", "protected_veteran"],
    "disability_status": ["disability", "disabled", "disability_status"],
}


# ---------------------------------------------------------------------------
# User data profile for autofill
# ---------------------------------------------------------------------------


@dataclass
class AutoFillProfile:
    """Personal/profile data used to fill forms automatically."""

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

    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    website: str = ""
    twitter_url: str = ""

    resume_path: str = ""
    cover_letter_text: str = ""

    salary_expectation: str = ""
    available_start_date: str = ""
    work_authorization: str = ""
    requires_sponsorship: str = ""

    gender: str = ""
    ethnicity: str = ""
    veteran_status: str = ""
    disability_status: str = ""

    highest_education: str = ""
    university: str = ""
    degree: str = ""
    graduation_year: str = ""

    years_experience: str = ""
    current_company: str = ""
    current_title: str = ""

    custom_fields: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_json(cls, path: str | Path) -> AutoFillProfile:
        with open(path) as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, str]:
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
# Field Matcher with Confidence Scoring
# ---------------------------------------------------------------------------


@dataclass
class FieldMatch:
    """Result of matching a form field to a profile attribute."""

    profile_attr: str
    confidence: float  # 0.0 to 1.0
    matched_by: str  # "template", "label", "name", "type", "fallback"
    value: str | None = None


class ConfidenceFieldMatcher:
    """
    Smart field matcher with confidence scoring.

    Priority order:
    1. ATS-specific template match → confidence 0.9-1.0
    2. Label text match → confidence 0.7-0.9
    3. Field name keyword match → confidence 0.4-0.8
    4. Input type heuristic → confidence 0.3-0.5
    5. No match → confidence 0.0 (don't fill)
    """

    def __init__(self, platform: str | None = None):
        self.platform = platform
        self.ats_fields: dict[str, list[str]] = {}

        # Load from external YAML template first
        if platform:
            template = load_template(platform)
            if template and "fields" in template:
                self.ats_fields = {k: list(v) for k, v in template["fields"].items()}

        # Fallback to built-in templates if YAML not found
        if not self.ats_fields and platform and platform in ATS_TEMPLATES:
            self.ats_fields = ATS_TEMPLATES[platform]

    def match(self, field: FormField) -> FieldMatch | None:
        """
        Match a form field to a profile attribute with confidence.

        Returns FieldMatch or None if no good match found.
        """
        name = field.name.lower().strip()
        label = (field.label_text or "").lower().strip()
        placeholder = (field.placeholder or "").lower().strip()
        ftype = field.field_type.lower()
        combined = f"{name} {label} {placeholder}"

        # Strategy 1: ATS template (highest confidence)
        if self.ats_fields:
            result = self._match_template(name, combined)
            if result and result.confidence >= 0.8:
                return result

        # Strategy 2: Label text match
        if label:
            result = self._match_by_text(label, "label")
            if result and result.confidence >= 0.7:
                return result

        # Strategy 3: Field name + placeholder keyword match
        result = self._match_by_text(combined, "name")
        if result and result.confidence >= 0.4:
            return result

        # Strategy 4: Type-based heuristic
        result = self._match_by_type(field)
        if result:
            return result

        return None

    def _match_template(self, name: str, combined: str) -> FieldMatch | None:
        """Match using ATS-specific field templates."""
        best_attr = None
        best_score = 0

        for profile_attr, field_names in self.ats_fields.items():
            for i, pattern in enumerate(field_names):
                if pattern.lower() == name:
                    # Exact match on field name — very high confidence
                    score = 1.0 - (i * 0.05)  # first match = 1.0, later = 0.95, etc.
                    if score > best_score:
                        best_score = score
                        best_attr = profile_attr
                    break
                elif pattern.lower() in combined:
                    score = 0.85 - (i * 0.05)
                    if score > best_score:
                        best_score = score
                        best_attr = profile_attr

        if best_attr and best_score >= 0.8:
            return FieldMatch(best_attr, best_score, "template")
        return None

    def _match_by_text(self, text: str, source: str) -> FieldMatch | None:
        """Match by keyword in label/name/placeholder text."""
        best_attr = None
        best_score = 0.0
        base_confidence = 0.75 if source == "label" else 0.55

        for profile_attr, keywords in GENERIC_FIELD_MAP.items():
            for kw in keywords:
                if kw == text or kw in text:
                    # Longer keyword = more specific = higher confidence
                    specificity = min(len(kw) / len(text), 1.0) if text else 0.5
                    score = base_confidence + (specificity * 0.2)

                    # Penalize very short matches (e.g., "name" matches too many things)
                    if len(kw) < 4:
                        score -= 0.1

                    if score > best_score:
                        best_score = score
                        best_attr = profile_attr
                    break

        if best_attr and best_score >= 0.4:
            conf = min(best_score, 0.95)
            return FieldMatch(best_attr, conf, source)
        return None

    def _match_by_type(self, field: FormField) -> FieldMatch | None:
        """Fallback: match by input type."""
        ftype = field.field_type.lower()
        name = field.name.lower()

        if ftype == "email":
            return FieldMatch("email", 0.4, "type")
        if ftype == "tel":
            return FieldMatch("phone", 0.35, "type")
        if ftype == "url":
            if "linkedin" in name:
                return FieldMatch("linkedin_url", 0.5, "type")
            if "github" in name:
                return FieldMatch("github_url", 0.5, "type")
            return FieldMatch("website", 0.3, "type")

        return None


# ---------------------------------------------------------------------------
# Auto-Filler (Updated)
# ---------------------------------------------------------------------------


@dataclass
class FillResult:
    """Result of filling a single field."""

    field_name: str
    field_label: str | None
    field_type: str
    value: str | None
    confidence: float
    matched_by: str
    profile_attr: str | None


class FormAutoFiller:
    """Automatically fill web forms using a user profile with confidence scoring."""

    CONFIDENCE_THRESHOLDS = {
        "high": 0.8,  # Fill automatically
        "medium": 0.5,  # Fill but flag for review
        "low": 0.3,  # Don't fill, suggest
        "skip": 0.0,  # Never fill
    }

    def __init__(self, profile: AutoFillProfile):
        self.profile = profile
        self.analyzer = FormAnalyzer()

    async def analyze_and_fill(self, url: str, html: str) -> list[dict[str, Any]]:
        """
        Analyze all forms on a page and generate fill data with confidence scores.
        """
        platform = detect_ats_platform(url, html)
        matcher = ConfidenceFieldMatcher(platform)
        forms = await self.analyzer.analyze_page(url, html)
        results: list[dict[str, Any]] = []

        for form in forms:
            fill_results: list[FillResult] = []
            fill_data: dict[str, str] = {}

            for field in form.fields:
                match = matcher.match(field)

                if match and match.confidence >= self.CONFIDENCE_THRESHOLDS["low"]:
                    value = self._get_profile_value(match.profile_attr, field)
                    match.value = value

                    if match.confidence >= self.CONFIDENCE_THRESHOLDS["medium"] and value:
                        fill_data[field.name] = value

                fill_results.append(
                    FillResult(
                        field_name=field.name,
                        field_label=field.label_text,
                        field_type=field.field_type,
                        value=match.value if match else None,
                        confidence=match.confidence if match else 0.0,
                        matched_by=match.matched_by if match else "none",
                        profile_attr=match.profile_attr if match else None,
                    )
                )

            high_conf = sum(1 for f in fill_results if f.confidence >= 0.8)
            med_conf = sum(1 for f in fill_results if 0.5 <= f.confidence < 0.8)
            low_conf = sum(1 for f in fill_results if 0.3 <= f.confidence < 0.5)
            no_conf = sum(1 for f in fill_results if f.confidence < 0.3)

            results.append(
                {
                    "form_url": form.url,
                    "form_action": form.action,
                    "form_method": form.method,
                    "form_purpose": form.purpose,
                    "platform": platform,
                    "fields_count": form.field_count,
                    "has_captcha": form.has_captcha,
                    "has_file_upload": form.has_file_upload,
                    "fill_data": fill_data,
                    "fill_results": [
                        {
                            "field_name": f.field_name,
                            "field_label": f.field_label,
                            "field_type": f.field_type,
                            "value": f.value,
                            "confidence": f.confidence,
                            "matched_by": f.matched_by,
                            "profile_attr": f.profile_attr,
                        }
                        for f in fill_results
                    ],
                    "confidence_summary": {
                        "high": high_conf,
                        "medium": med_conf,
                        "low": low_conf,
                        "none": no_conf,
                    },
                    "fill_coverage": len(fill_data) / max(form.field_count, 1),
                }
            )

        return results

    def _get_profile_value(self, profile_attr: str, field: FormField) -> str | None:
        """Get value from profile, handling select options."""
        value = getattr(self.profile, profile_attr, None)
        if not value:
            return None

        str_value = str(value)

        # Handle select fields: try to match an option
        if field.field_type == "select" and field.options:
            str_val_lower = str_value.lower()
            for option in field.options:
                if option.lower().strip() == str_val_lower:
                    return option
            # Partial match
            for option in field.options:
                if str_val_lower in option.lower() or option.lower() in str_val_lower:
                    return option
            # Yes/No matching
            if str_val_lower in ("yes", "true", "1"):
                for opt in field.options:
                    if opt.lower().strip() in ("yes", "true", "1", "i am", "i have"):
                        return opt
            elif str_val_lower in ("no", "false", "0"):
                for opt in field.options:
                    if opt.lower().strip() in ("no", "false", "0", "i am not", "i do not"):
                        return opt

        return str_value

    # ---- Script generation ----

    def generate_playwright_script(
        self,
        url: str,
        fill_results: list[dict],
        use_chrome: bool = False,
        chrome_user_data_dir: str | None = None,
    ) -> str:
        """Generate a Playwright Python script with confidence annotations."""
        lines = [
            '"""Auto-generated Playwright script for form filling."""',
            "import asyncio",
            "from playwright.async_api import async_playwright",
            "",
            "",
            "async def fill_forms():",
            "    async with async_playwright() as p:",
        ]

        if use_chrome:
            launch = "        browser = await p.chromium.launch(channel='chrome', headless=False"
            if chrome_user_data_dir:
                launch += ", args=['--user-data-dir=" + chrome_user_data_dir + "']"
            launch += ")"
            lines.append(launch)
        else:
            lines.append("        browser = await p.chromium.launch(headless=False)")

        lines.extend(
            [
                "        page = await browser.new_page()",
                f"        await page.goto('{url}')",
                "        await page.wait_for_load_state('networkidle')",
                "",
            ]
        )

        for i, result in enumerate(fill_results):
            fill_data = result.get("fill_data", {})
            fill_items = result.get("fill_results", [])

            if not fill_data:
                continue

            platform = result.get("platform", "unknown")
            lines.append(
                f"        # Form {i + 1}: {result.get('form_purpose', 'unknown')} [{platform}]"
            )
            lines.append(f"        # Action: {result.get('form_action', 'N/A')}")

            # High confidence fields → fill directly
            high = [
                (f["field_name"], f["value"])
                for f in fill_items
                if f.get("confidence", 0) >= 0.8 and f.get("value")
            ]
            medium = [
                (f["field_name"], f["value"])
                for f in fill_items
                if 0.5 <= f.get("confidence", 0) < 0.8 and f.get("value")
            ]
            low = [
                (f["field_name"], f["value"])
                for f in fill_items
                if 0.3 <= f.get("confidence", 0) < 0.5 and f.get("value")
            ]

            for name, value in high:
                escaped = value.replace("'", "\\'").replace("\n", "\\n")
                lines.append(
                    f"        await page.fill('[name=\"{name}\"]', '{escaped}')  # high confidence"
                )

            for name, value in medium:
                escaped = value.replace("'", "\\'").replace("\n", "\\n")
                lines.append(
                    f"        await page.fill('[name=\"{name}\"]', '{escaped}')  # REVIEW: medium confidence"
                )

            for name, value in low:
                escaped = value.replace("'", "\\'").replace("\n", "\\n")
                lines.append(
                    f"        # await page.fill('[name=\"{name}\"]', '{escaped}')  # LOW confidence — uncomment if correct"
                )

            lines.append("        # Uncomment to submit:")
            lines.append("        # await page.click('[type=\"submit\"]')")
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
        """Generate curl commands for direct HTTP form submission."""
        lines = ["#!/bin/bash", "# Auto-generated curl commands for form submission", ""]

        for i, result in enumerate(fill_results):
            fill_data = result.get("fill_data", {})
            if not fill_data:
                continue

            action = result.get("form_action", "")
            method = result.get("form_method", "post").upper()
            platform = result.get("platform", "unknown")

            lines.append(f"# Form {i + 1}: {result.get('form_purpose', 'unknown')} [{platform}]")

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
    """Fetch a URL, analyze its forms, and generate fill data."""
    if isinstance(profile, (str, Path)):
        profile = AutoFillProfile.from_json(profile)

    if html is None:
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text

    filler = FormAutoFiller(profile)
    return await filler.analyze_and_fill(url, html)


# ---------------------------------------------------------------------------
# Live Interactive Mode (Phase 2)
# ---------------------------------------------------------------------------

VISUAL_FEEDBACK_JS = """
(function() {
    // Spider-Nix Live Fill — Visual Feedback
    const style = document.createElement('style');
    style.textContent = `
        .spider-filled-high {
            border: 2px solid #22c55e !important;
            background-color: #f0fdf4 !important;
            box-shadow: 0 0 0 3px rgba(34,197,94,0.2) !important;
        }
        .spider-filled-medium {
            border: 2px solid #eab308 !important;
            background-color: #fefce8 !important;
            box-shadow: 0 0 0 3px rgba(234,179,8,0.2) !important;
        }
        .spider-filled-low {
            border: 2px solid #ef4444 !important;
            background-color: #fef2f2 !important;
        }
        .spider-tooltip {
            position: absolute;
            background: #1e293b;
            color: #f8fafc;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-family: monospace;
            z-index: 99999;
            pointer-events: none;
            white-space: nowrap;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .spider-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: bold;
            margin-left: 6px;
            font-family: monospace;
        }
        .spider-badge-high { background: #22c55e; color: #fff; }
        .spider-badge-medium { background: #eab308; color: #000; }
        .spider-badge-low { background: #ef4444; color: #fff; }
        .spider-banner {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 99998;
            background: linear-gradient(135deg, #1e293b, #334155);
            color: #f8fafc;
            padding: 12px 20px;
            font-family: monospace;
            font-size: 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }
        .spider-banner-left { display: flex; align-items: center; gap: 12px; }
        .spider-banner-right { display: flex; gap: 8px; font-size: 12px; }
        .spider-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
        .spider-dot-high { background: #22c55e; }
        .spider-dot-medium { background: #eab308; }
        .spider-dot-low { background: #ef4444; }
    `;
    document.head.appendChild(style);

    // Banner
    const banner = document.createElement('div');
    banner.className = 'spider-banner';
    banner.innerHTML = `
        <div class="spider-banner-left">
            <strong>🕷️ Spider-Nix Live Fill</strong>
            <span style="opacity:0.7">|</span>
            <span>Press <kbd style="background:#475569;padding:2px 8px;border-radius:4px">Enter</kbd> in terminal to submit</span>
        </div>
        <div class="spider-banner-right">
            <span><span class="spider-dot spider-dot-high"></span> Auto-filled</span>
            <span><span class="spider-dot spider-dot-medium"></span> Review</span>
            <span><span class="spider-dot spider-dot-low"></span> Manual</span>
        </div>
    `;
    document.body.insertBefore(banner, document.body.firstChild);
    document.body.style.paddingTop = '50px';
})();
"""


class LiveFormFiller:
    """
    Interactive live form filler using Playwright.

    Opens a browser, fills forms with visual feedback,
    and pauses for user review before submission.
    """

    def __init__(
        self,
        profile: AutoFillProfile,
        use_chrome: bool = False,
        chrome_user_data_dir: str | None = None,
        headless: bool = False,
    ):
        self.profile = profile
        self.use_chrome = use_chrome
        self.chrome_user_data_dir = chrome_user_data_dir
        self.headless = headless
        self.analyzer = FormAutoFiller(profile)

    async def fill_live(self, url: str) -> bool:
        """
        Open browser, fill forms live, wait for user review.

        Returns True if submitted, False if skipped.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install"
            )
            return False

        # Step 1: Analyze forms
        print("\n🔍 Analyzing forms...")
        import httpx

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text

        fill_results = await self.analyzer.analyze_and_fill(url, html)

        if not fill_results:
            print("❌ No forms found on this page.")
            return False

        # Print summary
        for i, fr in enumerate(fill_results):
            cs = fr.get("confidence_summary", {})
            platform = fr.get("platform") or "generic"
            print(f"\n📋 Form {i + 1}: {fr.get('form_purpose', 'unknown')} [{platform}]")
            print(
                f"   🟢 {cs.get('high', 0)} high  🟡 {cs.get('medium', 0)} medium  🔴 {cs.get('low', 0)} low  ⚫ {cs.get('none', 0)} none"
            )

        # Step 2: Launch browser
        print("\n🚀 Launching browser...")

        async with async_playwright() as p:
            launch_args: dict = {
                "headless": self.headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }

            if self.use_chrome:
                launch_args["channel"] = "chrome"
                if self.chrome_user_data_dir:
                    launch_args["args"].append(f"--user-data-dir={self.chrome_user_data_dir}")
                print(f"   Using system Chrome")
                if self.chrome_user_data_dir:
                    print(f"   Profile: {self.chrome_user_data_dir}")
            else:
                launch_args["args"].extend(["--disable-dev-shm-usage", "--no-sandbox"])

            browser = await p.chromium.launch(**launch_args)
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()

            # Step 3: Navigate
            print(f"\n📄 Navigating to {url}...")
            await page.goto(url, wait_until="networkidle")

            # Step 4: Inject visual feedback
            await page.evaluate(VISUAL_FEEDBACK_JS)
            await page.wait_for_timeout(500)

            # Step 5: Fill fields with confidence-based approach
            for fr in fill_results:
                fill_items = fr.get("fill_results", [])

                for item in fill_items:
                    name = item["field_name"]
                    value = item.get("value")
                    conf = item.get("confidence", 0)

                    if not value:
                        # Mark low-confidence empty fields
                        if conf < 0.3:
                            await self._mark_field(page, name, "low")
                        continue

                    try:
                        # Try to fill the field
                        await page.fill(f'[name="{name}"]', value, timeout=3000)

                        if conf >= 0.8:
                            await self._mark_field(page, name, "high")
                        elif conf >= 0.5:
                            await self._mark_field(page, name, "medium")
                        else:
                            await self._mark_field(page, name, "low")

                    except Exception as e:
                        logger.debug(f"Could not fill '{name}': {e}")
                        # Try select
                        try:
                            await page.select_option(f'[name="{name}"]', value, timeout=2000)
                            if conf >= 0.8:
                                await self._mark_field(page, name, "high")
                            elif conf >= 0.5:
                                await self._mark_field(page, name, "medium")
                        except Exception:
                            pass

            # Step 6: Pause for user review
            print("\n" + "=" * 50)
            print("👀 Review the form in the browser.")
            print(f"   🟢 Green  = auto-filled (high confidence)")
            print(f"   🟡 Yellow = auto-filled (review recommended)")
            print(f"   🔴 Red    = needs manual input")
            print()
            print("   Press [Enter] to submit all forms")
            print("   Press [S]     to skip submission (keep browser open)")
            print("   Press [Q]     to quit and close browser")
            print("=" * 50)

            choice = input("\n👉 ").strip().lower()

            if choice == "q":
                print("❌ Quit — closing browser.")
                await browser.close()
                return False
            elif choice == "s":
                print("⏸️  Skipped submission — browser stays open for manual editing.")
                print("   Close the browser window when done.")
                await page.wait_for_timeout(300_000)  # 5 min timeout
                return False
            else:
                # Enter = submit
                print("🚀 Submitting forms...")
                for fr in fill_results:
                    try:
                        # Click submit button
                        submit_btn = await page.query_selector(
                            'button[type="submit"], input[type="submit"], button:has-text("Submit"), button:has-text("Apply")'
                        )
                        if submit_btn:
                            await submit_btn.click()
                            await page.wait_for_timeout(2000)
                            print(f"   ✓ Submitted form: {fr.get('form_purpose', 'unknown')}")
                        else:
                            print(
                                f"   ⚠️  No submit button found for form: {fr.get('form_purpose', 'unknown')}"
                            )
                    except Exception as e:
                        print(f"   ✗ Submit failed: {e}")

                # Wait to see result
                print("\n⏳ Waiting 5 seconds to see result...")
                await page.wait_for_timeout(5000)
                await browser.close()
                print("✅ Done!")
                return True

    async def _mark_field(self, page, name: str, level: str) -> None:
        """Add visual class to a field."""
        class_map = {
            "high": "spider-filled-high",
            "medium": "spider-filled-medium",
            "low": "spider-filled-low",
        }
        css_class = class_map.get(level, "")
        if css_class:
            try:
                await page.evaluate(
                    f"""
                    (function() {{
                        const el = document.querySelector('[name="{name}"]');
                        if (el) {{
                            el.classList.add('{css_class}');
                            // Add badge after the field
                            const badge = document.createElement('span');
                            badge.className = 'spider-badge spider-badge-{level}';
                            badge.textContent = '{level}';
                            el.parentNode.appendChild(badge);
                        }}
                    }})();
                    """
                )
            except Exception:
                pass


async def live_fill_url(
    url: str,
    profile: AutoFillProfile | str | Path,
    use_chrome: bool = False,
    chrome_user_data_dir: str | None = None,
) -> bool:
    """Convenience: analyze and live-fill a URL."""
    if isinstance(profile, (str, Path)):
        profile = AutoFillProfile.from_json(profile)

    filler = LiveFormFiller(
        profile,
        use_chrome=use_chrome,
        chrome_user_data_dir=chrome_user_data_dir,
    )
    return await filler.fill_live(url)
