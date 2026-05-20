"""
Professional Job Intelligence Module — Core Data Models.

Provides structured job opportunity representation, company profiles,
and the foundation for multi-source aggregation, matching, and tracking.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    FREELANCE = "freelance"
    INTERNSHIP = "internship"
    COOP = "coop"


class RemotePolicy(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on_site"
    UNKNOWN = "unknown"


class Seniority(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    MANAGER = "manager"
    DIRECTOR = "director"
    VP = "vp"
    CXO = "cxo"
    UNKNOWN = "unknown"


class ApplicationStatus(str, Enum):
    SAVED = "saved"
    APPLIED = "applied"
    PHONE_SCREEN = "phone_screen"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    OFFER = "offer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class JobSource(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    BAMBOOHR = "bamboohr"
    REMOTEOK = "remoteok"
    WE_WORK_REMOTELY = "weworkremotely"
    HN_HIRING = "hackernews_hiring"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    COMPANY_CAREERS = "company_careers"
    GITHUB_JOBS = "github_jobs"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------


@dataclass
class Salary:
    """Normalized salary information."""

    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "USD"
    period: str = "yearly"  # yearly, monthly, hourly
    equity: str | None = None  # e.g. "0.01% - 0.05%"
    raw_text: str | None = None

    @property
    def display(self) -> str:
        if not self.min_amount and not self.max_amount:
            return self.raw_text or "Not disclosed"
        parts = []
        if self.min_amount:
            parts.append(f"{self.currency} {self.min_amount:,.0f}")
        if self.max_amount:
            parts.append(f"{self.currency} {self.max_amount:,.0f}")
        range_str = " – ".join(parts) if len(parts) > 1 else parts[0]
        if self.period != "yearly":
            range_str += f" / {self.period}"
        return range_str

    @property
    def midpoint(self) -> float | None:
        if self.min_amount and self.max_amount:
            return (self.min_amount + self.max_amount) / 2
        return self.min_amount or self.max_amount


# ---------------------------------------------------------------------------
# Company Profile
# ---------------------------------------------------------------------------


@dataclass
class CompanyProfile:
    """Information about the hiring company."""

    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None  # e.g. "50-200", "1000+"
    funding_stage: str | None = None  # Seed, Series A, etc.
    headquarters: str | None = None
    description: str | None = None
    crunchbase_url: str | None = None
    linkedin_url: str | None = None
    glassdoor_rating: float | None = None


# ---------------------------------------------------------------------------
# Job Opportunity (Core Model)
# ---------------------------------------------------------------------------


@dataclass
class JobOpportunity:
    """A single job opportunity with all extracted metadata."""

    # Identity
    id: str = ""  # Deterministic hash (url + title)
    source: JobSource = JobSource.OTHER
    source_url: str = ""

    # Core listing
    title: str = ""
    company: str = ""
    location: str = ""  # City, State, Country or "Remote"
    remote_policy: RemotePolicy = RemotePolicy.UNKNOWN
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    seniority: Seniority = Seniority.UNKNOWN

    # Description
    description: str = ""
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    qualifications: list[str] = field(default_factory=list)

    # Compensation
    salary: Salary | None = None

    # Tech
    tech_stack: list[str] = field(default_factory=list)

    # Application
    apply_url: str = ""  # Direct apply link (may differ from source_url)
    application_deadline: str | None = None

    # Timestamps
    date_posted: str | None = None
    date_found: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Metadata
    company_profile: CompanyProfile | None = None
    score: float = 0.0  # Internal relevance score (set by matcher or analyzer)
    match_details: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = self._generate_id()
        # Convert string enums
        if isinstance(self.source, str):
            try:
                self.source = JobSource(self.source)
            except ValueError:
                self.source = JobSource.OTHER
        if isinstance(self.remote_policy, str):
            try:
                self.remote_policy = RemotePolicy(self.remote_policy)
            except ValueError:
                self.remote_policy = RemotePolicy.UNKNOWN
        if isinstance(self.seniority, str):
            try:
                self.seniority = Seniority(self.seniority)
            except ValueError:
                self.seniority = Seniority.UNKNOWN
        if isinstance(self.employment_type, str):
            try:
                self.employment_type = EmploymentType(self.employment_type)
            except ValueError:
                self.employment_type = EmploymentType.FULL_TIME

    def _generate_id(self) -> str:
        raw = f"{self.source_url}|{self.title}|{self.company}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    def from_dict(cls, data: dict) -> JobOpportunity:
        """Deserialize from a dictionary (e.g. from storage or API)."""
        # Handle nested objects
        salary_data = data.pop("salary", None)
        salary = Salary(**salary_data) if salary_data else None

        company_data = data.pop("company_profile", None)
        company = CompanyProfile(**company_data) if company_data else None

        # Handle enums
        for field_name in ("remote_policy", "employment_type", "seniority", "source"):
            if field_name in data and isinstance(data[field_name], str):
                enum_cls = {
                    "remote_policy": RemotePolicy,
                    "employment_type": EmploymentType,
                    "seniority": Seniority,
                    "source": JobSource,
                }[field_name]
                try:
                    data[field_name] = enum_cls(data[field_name])
                except ValueError:
                    pass  # keep as-is

        return cls(salary=salary, company_profile=company, **data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat-ish dictionary for storage."""
        return {
            "id": self.id,
            "source": self.source.value,
            "source_url": self.source_url,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "remote_policy": self.remote_policy.value,
            "employment_type": self.employment_type.value,
            "seniority": self.seniority.value,
            "description": self.description,
            "requirements": self.requirements,
            "responsibilities": self.responsibilities,
            "benefits": self.benefits,
            "qualifications": self.qualifications,
            "tech_stack": self.tech_stack,
            "salary": {
                "min_amount": self.salary.min_amount if self.salary else None,
                "max_amount": self.salary.max_amount if self.salary else None,
                "currency": self.salary.currency if self.salary else "USD",
                "period": self.salary.period if self.salary else "yearly",
                "equity": self.salary.equity if self.salary else None,
                "raw_text": self.salary.raw_text if self.salary else None,
            },
            "apply_url": self.apply_url,
            "application_deadline": self.application_deadline,
            "date_posted": self.date_posted,
            "date_found": self.date_found,
            "score": self.score,
            "match_details": self.match_details,
            "company_profile": {
                "name": self.company_profile.name if self.company_profile else self.company,
                "domain": self.company_profile.domain if self.company_profile else None,
                "industry": self.company_profile.industry if self.company_profile else None,
                "size": self.company_profile.size if self.company_profile else None,
                "funding_stage": self.company_profile.funding_stage
                if self.company_profile
                else None,
                "headquarters": self.company_profile.headquarters if self.company_profile else None,
                "description": self.company_profile.description if self.company_profile else None,
                "crunchbase_url": self.company_profile.crunchbase_url
                if self.company_profile
                else None,
                "linkedin_url": self.company_profile.linkedin_url if self.company_profile else None,
                "glassdoor_rating": self.company_profile.glassdoor_rating
                if self.company_profile
                else None,
            },
        }

    def summary(self) -> str:
        """One-line summary for terminal display."""
        parts = [
            f"[{self.source.value}]",
            self.title or "Untitled",
            f"@ {self.company}",
        ]
        if self.location:
            parts.append(f"📍 {self.location}")
        if self.remote_policy != RemotePolicy.UNKNOWN:
            parts.append(f"🏠 {self.remote_policy.value}")
        if self.salary and self.salary.midpoint:
            parts.append(f"💰 {self.salary.display}")
        if self.seniority != Seniority.UNKNOWN:
            parts.append(f"🎯 {self.seniority.value}")
        if self.score:
            parts.append(f"⭐ {self.score:.1f}")
        return "  ".join(parts)


# ---------------------------------------------------------------------------
# Regex helpers (shared across job modules)
# ---------------------------------------------------------------------------

# Salary patterns
SALARY_PATTERNS = [
    # $100k - $150k
    re.compile(
        r"(?P<currency>[\$\€\£\¥])\s*"
        r"(?P<min>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*[kK]?\s*[-–—to]+\s*"
        r"(?:(?P<currency2>[\$\€\£\¥])\s*)?"
        r"(?P<max>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*[kK]?"
    ),
    # $100,000 - $150,000 USD
    re.compile(
        r"(?P<currency>[\$\€\£\¥])\s*"
        r"(?P<min>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*"
        r"(?:USD|EUR|GBP|JPY|BRL)?\s*[-–—to]+\s*"
        r"(?:(?P<currency2>[\$\€\£\¥])\s*)?"
        r"(?P<max>\d{1,3}(?:,\d{3})*(?:\.\d+)?)"
    ),
    # R$ 5.000 - R$ 10.000 (Brazilian Real)
    re.compile(
        r"(?:(?P<currency>R\$)\s*)?"
        r"(?P<min>\d{1,3}(?:\.\d{3})*(?:,\d+)?)\s*[-–—to]+\s*"
        r"(?:(?:R\$)\s*)?"
        r"(?P<max>\d{1,3}(?:\.\d{3})*(?:,\d+)?)",
    ),
]

TECH_KEYWORDS: dict[str, list[str]] = {
    "Python": ["python", "django", "flask", "fastapi"],
    "JavaScript": ["javascript", "js", "es6", "node"],
    "TypeScript": ["typescript", "ts"],
    "React": ["react", "reactjs", "react.js", "next.js", "nextjs"],
    "Vue": ["vue", "vuejs", "vue.js", "nuxt"],
    "Angular": ["angular", "angularjs"],
    "Node.js": ["node.js", "nodejs", "express", "nest.js", "nestjs"],
    "Rust": ["rust", "rustlang"],
    "Go": ["go", "golang"],
    "Java": ["java", "spring", "springboot"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift", "swiftui"],
    "C#": ["c#", "csharp", ".net", "dotnet"],
    "Ruby": ["ruby", "rails", "ruby on rails"],
    "PHP": ["php", "laravel", "symfony"],
    "Scala": ["scala"],
    "Elixir": ["elixir", "phoenix"],
    "Clojure": ["clojure"],
    "Haskell": ["haskell"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Docker": ["docker"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Nix": ["nix", "nixos", "nixpkgs"],
    "GraphQL": ["graphql"],
    "gRPC": ["grpc"],
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Kafka": ["kafka"],
    "RabbitMQ": ["rabbitmq"],
    "CI/CD": ["ci/cd", "ci cd", "continuous integration"],
    "Git": ["git"],
    "Linux": ["linux"],
    "ML/AI": ["machine learning", "ml", "ai", "llm", "gpt", "transformer"],
    "Data Engineering": ["data engineer", "spark", "hadoop", "snowflake", "databricks"],
    "DevOps": ["devops", "sre", "platform engineer"],
    "Security": ["security", "appsec", "infosec", "pentest"],
    "Blockchain": ["blockchain", "web3", "solidity", "crypto"],
}


def extract_salary(text: str) -> Salary | None:
    """Extract salary information from text using regex patterns."""
    for pattern in SALARY_PATTERNS:
        match = pattern.search(text)
        if match:
            min_str = match.group("min").replace(",", "").replace(".", "")
            max_str = match.group("max").replace(",", "").replace(".", "")

            currency = match.group("currency") or match.group("currency2") or "$"
            currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "R$": "BRL"}
            currency = currency_map.get(currency, currency)

            try:
                min_val = float(min_str)
                max_val = float(max_str)
                # If values look like they're in thousands (e.g. "100" meaning "100k")
                if min_val < 1000 and "k" in match.group(0).lower():
                    min_val *= 1000
                    max_val *= 1000
                return Salary(
                    min_amount=min_val,
                    max_amount=max_val,
                    currency=currency,
                    raw_text=match.group(0).strip(),
                )
            except ValueError:
                continue
    return None


def extract_tech_stack(text: str) -> list[str]:
    """Extract technology mentions from text."""
    text_lower = text.lower()
    found: list[str] = []
    for tech, keywords in TECH_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                found.append(tech)
                break
    return found


def extract_seniority(text: str) -> Seniority:
    """Determine seniority level from text."""
    text_lower = text.lower()
    checks: list[tuple[str, Seniority]] = [
        ("principal", Seniority.PRINCIPAL),
        ("staff engineer", Seniority.STAFF),
        ("staff software", Seniority.STAFF),
        ("senior staff", Seniority.STAFF),
        ("senior principal", Seniority.PRINCIPAL),
        ("senior director", Seniority.DIRECTOR),
        ("director of", Seniority.DIRECTOR),
        ("vp of", Seniority.VP),
        ("head of", Seniority.MANAGER),
        ("engineering manager", Seniority.MANAGER),
        ("tech lead", Seniority.LEAD),
        ("technical lead", Seniority.LEAD),
        ("team lead", Seniority.LEAD),
        ("senior", Seniority.SENIOR),
        ("sr.", Seniority.SENIOR),
        ("mid-level", Seniority.MID),
        ("mid level", Seniority.MID),
        ("junior", Seniority.JUNIOR),
        ("jr.", Seniority.JUNIOR),
        ("intern", Seniority.INTERN),
        ("estágio", Seniority.INTERN),
        ("estagiário", Seniority.INTERN),
    ]
    for phrase, level in checks:
        if phrase in text_lower:
            return level
    return Seniority.UNKNOWN


def extract_remote_policy(text: str) -> RemotePolicy:
    """Determine remote work policy from text."""
    text_lower = text.lower()
    if any(
        w in text_lower for w in ["remote-first", "remote first", "fully remote", "100% remote"]
    ):
        return RemotePolicy.REMOTE
    if any(w in text_lower for w in ["remote", "trabalho remoto", "home office"]):
        if any(w in text_lower for w in ["hybrid", "híbrido", "flexible"]):
            return RemotePolicy.HYBRID
        return RemotePolicy.REMOTE
    if any(w in text_lower for w in ["hybrid", "híbrido"]):
        return RemotePolicy.HYBRID
    if any(w in text_lower for w in ["on-site", "onsite", "presencial", "in-office"]):
        return RemotePolicy.ON_SITE
    return RemotePolicy.UNKNOWN


def extract_employment_type(text: str) -> EmploymentType:
    """Determine employment type from text."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["contract", "contrato", "b2b"]):
        return EmploymentType.CONTRACT
    if any(w in text_lower for w in ["freelance", "freela", "pj"]):
        return EmploymentType.FREELANCE
    if any(w in text_lower for w in ["part-time", "part time", "meio período"]):
        return EmploymentType.PART_TIME
    if any(w in text_lower for w in ["internship", "intern", "estágio", "estagiário"]):
        return EmploymentType.INTERNSHIP
    if any(w in text_lower for w in ["co-op", "coop"]):
        return EmploymentType.COOP
    return EmploymentType.FULL_TIME
