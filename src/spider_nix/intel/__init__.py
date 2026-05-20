"""Job Intelligence — professional job hunt toolkit."""

from spider_nix.intel.form_filler import AutoFillProfile, FormAutoFiller, autofill_url
from spider_nix.intel.job_ats import (
    AshbyScraper,
    ATSScraperResult,
    CareerPageDiscoverer,
    GreenhouseScraper,
    LeverScraper,
    discover_and_scrape,
)
from spider_nix.intel.job_matcher import (
    JobScorer,
    JobSeekerProfile,
    PreferredRemote,
    match_jobs,
)
from spider_nix.intel.job_scrapers import (
    HNHiringScraper,
    RemoteOKScraper,
    WeWorkRemotelyScraper,
    scrape_all_boards,
)
from spider_nix.intel.job_storage import JobStorage
from spider_nix.intel.job_tracker import ApplicationTracker
from spider_nix.intel.jobs import (
    ApplicationStatus,
    CompanyProfile,
    EmploymentType,
    JobOpportunity,
    JobSource,
    RemotePolicy,
    Salary,
    Seniority,
    extract_employment_type,
    extract_remote_policy,
    extract_salary,
    extract_seniority,
    extract_tech_stack,
)

__all__ = [
    # Data models
    "JobOpportunity",
    "Salary",
    "CompanyProfile",
    # Enums
    "JobSource",
    "EmploymentType",
    "RemotePolicy",
    "Seniority",
    "ApplicationStatus",
    "PreferredRemote",
    # Extractors
    "extract_salary",
    "extract_tech_stack",
    "extract_seniority",
    "extract_remote_policy",
    "extract_employment_type",
    # ATS scrapers
    "GreenhouseScraper",
    "LeverScraper",
    "AshbyScraper",
    "CareerPageDiscoverer",
    "ATSScraperResult",
    "discover_and_scrape",
    # Job board scrapers
    "RemoteOKScraper",
    "WeWorkRemotelyScraper",
    "HNHiringScraper",
    "scrape_all_boards",
    # Matching
    "JobSeekerProfile",
    "JobScorer",
    "match_jobs",
    # Form auto-filler
    "AutoFillProfile",
    "FormAutoFiller",
    "autofill_url",
    # Storage & tracking
    "JobStorage",
    "ApplicationTracker",
]
