"""Tests for job discovery and email monitor modules."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from spider_nix.intel.email_monitor import _classify_email, _extract_company
from spider_nix.intel.job_discovery import JobDiscovery


# ── Discovery ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remoteok_fetch_and_filter(mock_profile):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"legal": "..."},
        {
            "position": "Security Architect",
            "company": "AcmeCorp",
            "tags": ["security", "rust", "nixos"],
            "description": "Remote security architect role with Rust and NixOS.",
            "apply_url": "https://acmecorp.com/apply",
            "url": "https://remoteok.com/jobs/123",
            "salary_min": 90000,
            "salary_max": 150000,
        },
        {
            "position": "Junior PHP Developer",
            "company": "OtherCorp",
            "tags": ["php"],
            "description": "PHP development.",
            "apply_url": "https://othercorp.com/apply",
            "url": "https://remoteok.com/jobs/456",
        },
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        discovery = JobDiscovery(mock_profile)
        jobs = await discovery._fetch_remoteok()

    assert len(jobs) == 1
    assert jobs[0].company == "AcmeCorp"
    assert jobs[0].salary_range is not None


@pytest.mark.asyncio
async def test_greenhouse_board_fetch(mock_profile):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "jobs": [
            {
                "title": "Platform Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "content": "Remote platform engineering role with NixOS and Kubernetes.",
            },
            {
                "title": "Marketing Manager",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/456",
                "content": "Lead marketing campaigns.",
            },
        ]
    }

    keywords = ["platform engineer", "nixos", "security"]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        discovery = JobDiscovery(mock_profile)
        jobs = await discovery._fetch_greenhouse_board("Acme", "acme", keywords)

    assert len(jobs) == 1
    assert jobs[0].title == "Platform Engineer"


def test_keywords_lower(mock_profile):
    discovery = JobDiscovery(mock_profile)
    keywords = discovery._keywords_lower()
    assert all(k == k.lower() for k in keywords)
    assert len(keywords) > 0


def test_matches_keywords(mock_profile):
    discovery = JobDiscovery(mock_profile)
    keywords = ["security architect", "nixos", "rust"]
    assert discovery._matches_keywords("senior security architect role remote", keywords)
    assert not discovery._matches_keywords("junior php developer", keywords)


def test_detect_remote_policy(mock_profile):
    discovery = JobDiscovery(mock_profile)
    assert discovery._detect_remote_policy("fully remote position") == "Remote"
    assert discovery._detect_remote_policy("hybrid work model") == "Hybrid"
    assert discovery._detect_remote_policy("on-site required") == "On-site"
    assert discovery._detect_remote_policy("no mention") is None


# ── Email classification ────────────────────────────────────────────────────────


def test_classify_rejection():
    cls, conf = _classify_email(
        subject="Your application to Acme",
        body="Unfortunately, we have decided not to move forward with your application.",
    )
    assert cls == "rejection"
    assert conf > 0.8


def test_classify_interview():
    cls, conf = _classify_email(
        subject="Next steps — Security Architect role",
        body="We'd like to schedule an interview with you. Please use the Calendly link below.",
    )
    assert cls == "interview_invite"
    assert conf > 0.8


def test_classify_offer():
    cls, conf = _classify_email(
        subject="Offer of Employment",
        body="We are pleased to offer you the position of Security Architect.",
    )
    assert cls == "offer"
    assert conf > 0.9


def test_classify_followup():
    cls, conf = _classify_email(
        subject="Thank you for applying",
        body="We received your application and are currently reviewing candidates.",
    )
    assert cls == "followup"
    assert conf > 0.7


def test_classify_unknown():
    cls, conf = _classify_email(
        subject="Newsletter from TechCorp",
        body="Here are the latest industry updates...",
    )
    assert cls == "unknown"
    assert conf == 0.0


def test_extract_company_from_name():
    company = _extract_company("Cloudflare Recruiting <noreply@greenhouse.io>", "")
    assert company == "Cloudflare Recruiting"


def test_extract_company_from_domain():
    company = _extract_company("<noreply@stripe.com>", "")
    assert company is not None
    assert "stripe" in company.lower()


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_profile():
    from spider_nix.intel.profile import (
        Experience,
        PersonalInfo,
        Preferences,
        Profile,
    )

    profile = Profile(
        personal=PersonalInfo(
            name="Test User",
            email="test@test.com",
            phone="+55",
            location="Brazil",
            linkedin="linkedin.com/in/test",
            github="github.com/test",
            website="test.com",
            timezone="America/Bahia",
        ),
        current_experience=Experience(
            title="Security Architect",
            company="voidnxlabs",
            start="2024-03",
        ),
        primary_skills=["Rust", "NixOS", "eBPF", "Security Architecture"],
        secondary_skills=["Python", "Kubernetes"],
        languages=["Portuguese", "English"],
        preferences=Preferences(
            remote_only=True,
            min_salary_usd=80000,
            target_roles=["Security Architect", "Platform Engineer"],
            dealbreakers=["on-site", "junior only"],
        ),
        cover_letter_template="Test cover letter.",
        llm_api_url="http://localhost:9000",
        llm_model="mistral",
    )
    setattr(
        profile,
        "_discovery_cfg",
        {
            "sources": ["remoteok", "companies"],
            "keywords": ["security architect", "platform engineer", "nixos", "rust"],
            "min_score": 40.0,
            "interval_hours": 4,
            "companies": [],
        },
    )
    return profile
