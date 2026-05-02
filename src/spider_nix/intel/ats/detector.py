"""ATS platform detection from URL and page content."""

from enum import Enum
from urllib.parse import urlparse


class ATSPlatform(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    BAMBOOHR = "bamboohr"
    GENERIC = "generic"


ATS_URL_PATTERNS: dict[str, ATSPlatform] = {
    "boards.greenhouse.io": ATSPlatform.GREENHOUSE,
    "greenhouse.io": ATSPlatform.GREENHOUSE,
    "jobs.lever.co": ATSPlatform.LEVER,
    "lever.co": ATSPlatform.LEVER,
    "jobs.ashbyhq.com": ATSPlatform.ASHBY,
    "ashbyhq.com": ATSPlatform.ASHBY,
    "myworkdayjobs.com": ATSPlatform.WORKDAY,
    "workday.com": ATSPlatform.WORKDAY,
    "careers.smartrecruiters.com": ATSPlatform.SMARTRECRUITERS,
    "smartrecruiters.com": ATSPlatform.SMARTRECRUITERS,
    "bamboohr.com": ATSPlatform.BAMBOOHR,
}


def detect_from_url(url: str) -> ATSPlatform:
    """Detect ATS platform from URL."""
    netloc = urlparse(url).netloc.lower()
    for pattern, platform in ATS_URL_PATTERNS.items():
        if pattern in netloc:
            return platform
    return ATSPlatform.GENERIC


def detect_from_html(html: str) -> ATSPlatform:
    """Fallback detection from page HTML."""
    html_lower = html.lower()
    if "greenhouse" in html_lower or "grnh.se" in html_lower:
        return ATSPlatform.GREENHOUSE
    if "lever.co" in html_lower:
        return ATSPlatform.LEVER
    if "ashby" in html_lower:
        return ATSPlatform.ASHBY
    if "workday" in html_lower:
        return ATSPlatform.WORKDAY
    return ATSPlatform.GENERIC

