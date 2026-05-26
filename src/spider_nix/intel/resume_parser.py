"""
Resume Parser — extract structured data from PDF, DOCX, and TXT resumes.

Populates AutoFillProfile and JobSeekerProfile for downstream job matching
and form auto-filling.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resume_log_label(path: Path) -> str:
    """Return non-identifying metadata for resume log messages."""
    suffix = path.suffix.lower() or "<none>"
    return f"suffix={suffix}"


@dataclass
class ResumeData:
    """Structured data extracted from a resume."""

    raw_text: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    github_url: str = ""
    portfolio_url: str = ""

    skills: list[str] = field(default_factory=list)
    years_experience: float = 0.0
    current_title: str = ""
    current_company: str = ""

    education: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)

    def to_autofill_profile(self):
        """Convert to AutoFillProfile."""
        from spider_nix.intel.form_filler import AutoFillProfile

        return AutoFillProfile(
            full_name=self.name,
            first_name=self.name.split()[0] if self.name else "",
            last_name=self.name.split()[-1] if len(self.name.split()) > 1 else "",
            email=self.email,
            phone=self.phone,
            location=self.location,
            linkedin_url=self.linkedin_url,
            github_url=self.github_url,
            portfolio_url=self.portfolio_url,
            years_experience=str(int(self.years_experience)) if self.years_experience else "",
            current_title=self.current_title,
            current_company=self.current_company,
        )

    def to_job_seeker_profile(self):
        """Convert to JobSeekerProfile."""
        from spider_nix.intel.job_matcher import JobSeekerProfile, PreferredRemote, Seniority

        seniority = Seniority.UNKNOWN
        if self.years_experience >= 8:
            seniority = Seniority.STAFF
        elif self.years_experience >= 5:
            seniority = Seniority.SENIOR
        elif self.years_experience >= 2:
            seniority = Seniority.MID
        elif self.years_experience >= 0:
            seniority = Seniority.JUNIOR

        return JobSeekerProfile(
            skills=self.skills,
            years_experience=self.years_experience,
            current_seniority=seniority,
            target_seniority=[seniority],
            preferred_remote=PreferredRemote.REMOTE_PREFERRED,
            desired_titles=[self.current_title] if self.current_title else [],
        )

    def summary(self) -> str:
        lines = [f"👤 {self.name or '(not found)'}"]
        if self.email:
            lines.append(f"📧 {self.email}")
        if self.phone:
            lines.append(f"📞 {self.phone}")
        if self.location:
            lines.append(f"📍 {self.location}")
        if self.skills:
            lines.append(f"🛠️  {', '.join(self.skills[:15])}")
        if self.years_experience:
            lines.append(f"⏳ {self.years_experience:.1f} years experience")
        if self.current_title:
            lines.append(
                f"💼 {self.current_title}"
                + (f" @ {self.current_company}" if self.current_company else "")
            )
        if self.education:
            lines.append(f"🎓 {self.education[0]}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------


def read_pdf(path: Path) -> str:
    """Extract text from a PDF file."""
    # Try pypdf first
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        if text.strip():
            return text
    except ImportError:
        logger.debug("pypdf not installed, trying fallback...")
    except Exception as e:
        logger.debug(f"pypdf failed: {e}")

    # Try pdfplumber
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
    except ImportError:
        logger.debug("pdfplumber not installed")
    except Exception as e:
        logger.debug(f"pdfplumber failed: {e}")

    # Last resort: read raw bytes and extract ASCII strings
    try:
        raw = path.read_bytes()
        # Extract printable ASCII sequences
        text = ""
        current = []
        for byte in raw:
            if 32 <= byte < 127 or byte in (10, 13):
                current.append(chr(byte))
            else:
                if len(current) > 3:
                    text += "".join(current) + " "
                current = []
        if current:
            text += "".join(current)
        return text
    except Exception:
        pass

    return ""


def read_docx(path: Path) -> str:
    """Extract text from a DOCX file (ZIP of XML)."""
    try:
        import zipfile
        from xml.etree import ElementTree as ET

        with zipfile.ZipFile(str(path)) as z:
            if "word/document.xml" not in z.namelist():
                return ""

            xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)

            # Extract all text from <w:t> elements
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                texts = []
                for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                    if t.text:
                        texts.append(t.text)
                if texts:
                    paragraphs.append("".join(texts))

            return "\n".join(paragraphs)
    except Exception as e:
        logger.debug(f"DOCX read failed: {e}")
        return ""


def read_txt(path: Path) -> str:
    """Read a plain text file."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def extract_text(path: Path) -> str:
    """Extract text from any supported resume format."""
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf(path)
    elif suffix in (".docx", ".doc"):
        return read_docx(path)
    elif suffix in (".txt", ".text", ".md", ".rst"):
        return read_txt(path)
    else:
        # Try as plain text
        return read_txt(path)


# ---------------------------------------------------------------------------
# Structured data extractors
# ---------------------------------------------------------------------------


def extract_email(text: str) -> str:
    """Extract the first email address found."""
    match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
    return match.group(0) if match else ""


def extract_phone(text: str) -> str:
    """Extract the first phone number found."""
    patterns = [
        r"\+\d{1,3}\s?\d{1,3}\s?\d{4,5}[-.\s]?\d{4}",  # +55 11 99999-9999
        r"\(\d{2,3}\)\s?\d{4,5}[-.\s]?\d{4}",  # (11) 99999-9999
        r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",  # 123-456-7890
        r"\d{4,5}[-.\s]?\d{4}",  # 99999-9999 (BR)
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def extract_linkedin(text: str) -> str:
    """Extract LinkedIn profile URL."""
    match = re.search(r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+", text)
    return match.group(0) if match else ""


def extract_github(text: str) -> str:
    """Extract GitHub profile URL."""
    match = re.search(r"https?://(?:www\.)?github\.com/[A-Za-z0-9_-]+", text)
    if match:
        url = match.group(0)
        # Filter out common false positives
        if not any(x in url.lower() for x in ["/issues", "/pull", "/blob", "/tree", "/releases"]):
            return url
    return ""


def extract_portfolio(text: str) -> str:
    """Extract portfolio/personal website URL."""
    # Look for URLs that aren't LinkedIn or GitHub
    url_pattern = r"https?://[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}(?:/[^\s]*)?"
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        if "linkedin.com" not in url and "github.com" not in url:
            return url
    return ""


def extract_name(text: str, email: str = "") -> str:
    """
    Extract name from resume text.

    Strategy: first non-empty line that looks like a name
    (contains only letters/spaces, 2-4 words, each starting with uppercase).
    """
    lines = text.strip().split("\n")

    # If we have email, look for name near it
    if email:
        email_line_idx = -1
        for i, line in enumerate(lines):
            if email in line:
                email_line_idx = i
                break
        # Check lines above email
        if email_line_idx > 0:
            for offset in range(1, min(5, email_line_idx + 1)):
                candidate = lines[email_line_idx - offset].strip()
                if _looks_like_name(candidate):
                    return candidate

    # Check first few lines
    for line in lines[:20]:
        candidate = line.strip()
        if _looks_like_name(candidate):
            return candidate

    return ""


def _looks_like_name(text: str) -> bool:
    """Check if a text string looks like a person's name."""
    # Filter out common non-name lines
    skip_patterns = [
        r"resume",
        r"curriculum",
        r"cv",
        r"curriculo",
        r"phone",
        r"email",
        r"address",
        r"summary",
        r"objective",
        r"experience",
        r"education",
        r"skills?",
        r"reference",
        r"http",
        r"www\.",
        r"@",
    ]
    text_lower = text.lower()
    for pat in skip_patterns:
        if re.search(pat, text_lower):
            return False

    # Name characteristics
    words = text.split()
    if not (2 <= len(words) <= 5):
        return False

    # Each word should start with uppercase or be a known connector
    connectors = {"de", "da", "do", "dos", "das", "e", "van", "von", "di", "del", "y"}
    for word in words:
        if word.lower() in connectors:
            continue
        if not word[0].isupper():
            return False
        # Should be mostly letters
        if not re.match(r"^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'-]*$", word):
            return False

    return True


def extract_skills(text: str) -> list[str]:
    """Extract skills from text by matching against known tech keywords."""
    from spider_nix.intel.jobs import TECH_KEYWORDS

    text_lower = text.lower()
    found: list[str] = []

    for tech, keywords in TECH_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(tech)
                break

    return found


def extract_years_experience(text: str) -> float:
    """Estimate years of experience from resume text."""
    total_years = 0.0
    date_ranges: list[tuple[int, int]] = []

    # Pattern: "2019 - 2023" or "Jan 2019 - Present" or "2019 - 2023 (4 years)"
    patterns = [
        r"(\d{4})\s*[-–—to]+\s*(\d{4}|Present|Current|present|current|Atual|atual)",
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s*[-–—to]+\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?\s*(\d{4}|Present|Current)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            start = int(match.group(1))
            end_str = match.group(2)
            if end_str.lower() in ("present", "current", "atual"):
                import datetime

                end = datetime.datetime.now().year
            else:
                end = int(end_str)
            if 1990 <= start <= 2030 and 1990 <= end <= 2030 and start <= end:
                date_ranges.append((start, end))

    # Deduplicate overlapping ranges
    if date_ranges:
        date_ranges.sort()
        merged = [date_ranges[0]]
        for start, end in date_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))

        total_years = sum(end - start for start, end in merged)

    # Also check for explicit mentions: "5 years of experience"
    if total_years == 0:
        exp_match = re.search(r"(\d+)\+?\s*years?\s*(?:of\s*)?experience", text, re.IGNORECASE)
        if exp_match:
            total_years = float(exp_match.group(1))

    return round(total_years, 1)


def extract_current_position(text: str) -> tuple[str, str]:
    """Extract current job title and company."""
    title = ""
    company = ""

    # Look for "Present" or "Current" in experience section
    # Try to find the most recent position
    lines = text.split("\n")
    experience_section = False
    most_recent_lines: list[str] = []

    for i, line in enumerate(lines):
        line_lower = line.lower().strip()

        # Detect experience section
        if any(
            kw in line_lower
            for kw in ["experience", "employment", "work history", "experiência", "experiencia"]
        ):
            experience_section = True
            continue
        elif experience_section and any(
            kw in line_lower for kw in ["education", "skills", "projects"]
        ):
            experience_section = False
            continue

        if experience_section and line.strip():
            most_recent_lines.append(line.strip())
            if len(most_recent_lines) > 10:
                break

    # Look for "Present" or date ranges in recent lines
    for i, line in enumerate(most_recent_lines):
        if re.search(r"(Present|Current|Atual)", line):
            # Title is usually the line above company/date
            if i > 0:
                candidate = most_recent_lines[i - 1]
                if not re.search(r"\d{4}", candidate):  # Not a date
                    title = candidate.strip().rstrip(",")
            # Company might be 2 lines above
            if i > 1 and not title:
                title = most_recent_lines[i - 2].strip().rstrip(",")

            # Company is often in the same line or adjacent
            # Pattern: "Company Name | Date - Present"
            company_match = re.search(r"^([A-Za-z0-9\s&.,]+?)\s*[|\-–—]", line)
            if company_match:
                company = company_match.group(1).strip()
            elif i > 0:
                company = most_recent_lines[i - 1].strip().rstrip(",")

            break

    return title, company


def extract_education(text: str) -> list[str]:
    """Extract education entries."""
    education: list[str] = []
    lines = text.split("\n")
    edu_section = False

    degree_keywords = [
        "bachelor",
        "master",
        "phd",
        "doctorate",
        "mba",
        "associate",
        "bacharel",
        "mestre",
        "doutor",
        "licenciatura",
        "tecnólogo",
        "b.s.",
        "m.s.",
        "b.a.",
        "m.a.",
        "ph.d.",
        "m.b.a.",
    ]

    for line in lines:
        line_lower = line.lower().strip()

        if any(
            kw in line_lower
            for kw in ["education", "academic", "educação", "formação", "educacion"]
        ):
            edu_section = True
            continue
        elif edu_section and any(kw in line_lower for kw in ["experience", "skills", "projects"]):
            edu_section = False
            continue

        if edu_section and line.strip():
            if any(kw in line_lower for kw in degree_keywords):
                education.append(line.strip())
            elif (
                "university" in line_lower
                or "universidade" in line_lower
                or "college" in line_lower
                or "faculdade" in line_lower
            ):
                education.append(line.strip())

            if len(education) >= 5:
                break

    return education


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_resume(path: str | Path) -> ResumeData:
    """
    Parse a resume file and extract structured data.

    Supports: PDF, DOCX, TXT

    Returns a ResumeData object with extracted information.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Resume file not found: {path}")

    logger.info("Parsing resume file (%s)", _resume_log_label(path))

    # Step 1: Extract raw text
    raw_text = extract_text(path)

    if not raw_text.strip():
        raise ValueError(f"Could not extract text from {path}. Unsupported format or empty file.")

    # Step 2: Extract structured fields
    email = extract_email(raw_text)
    phone = extract_phone(raw_text)
    name = extract_name(raw_text, email)
    linkedin = extract_linkedin(raw_text)
    github = extract_github(raw_text)
    portfolio = extract_portfolio(raw_text)
    skills = extract_skills(raw_text)
    years_exp = extract_years_experience(raw_text)
    current_title, current_company = extract_current_position(raw_text)
    education = extract_education(raw_text)

    data = ResumeData(
        raw_text=raw_text[:5000],
        name=name,
        email=email,
        phone=phone,
        location="",  # Hard to extract reliably, leave empty
        linkedin_url=linkedin,
        github_url=github,
        portfolio_url=portfolio,
        skills=skills,
        years_experience=years_exp,
        current_title=current_title,
        current_company=current_company,
        education=education,
    )

    logger.info(
        "Resume parsed: fields=%s, skills=%d, exp=%.1fy",
        {
            "name": bool(name),
            "email": bool(email),
            "phone": bool(phone),
            "linkedin": bool(linkedin),
            "github": bool(github),
            "portfolio": bool(portfolio),
        },
        len(skills),
        years_exp,
    )

    return data
