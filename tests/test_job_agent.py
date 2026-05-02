"""Tests for job agent modules."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from spider_nix.intel.approval_gate import ApprovalContext
from spider_nix.intel.ats.api_submit import SubmitResult, greenhouse_api_submit, lever_api_submit
from spider_nix.intel.ats.detector import ATSPlatform, detect_from_url
from spider_nix.intel.jobs import JobOpportunity
from spider_nix.intel.personal_scorer import score_opportunity


def test_ats_detection():
    assert detect_from_url("https://boards.greenhouse.io/acme/jobs/123") == ATSPlatform.GREENHOUSE
    assert detect_from_url("https://jobs.lever.co/acme/abc-def-123") == ATSPlatform.LEVER
    assert detect_from_url("https://jobs.ashbyhq.com/acme/123") == ATSPlatform.ASHBY
    assert detect_from_url("https://acme.myworkdayjobs.com/en-US/jobs") == ATSPlatform.WORKDAY
    assert detect_from_url("https://careers.example.com/jobs/123") == ATSPlatform.GENERIC


def test_personal_scorer_dealbreaker(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp",
        url="https://example.com",
        remote_policy="on-site",
        tech_stack=["Rust", "NixOS"],
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert score == 0.0
    assert any("DEALBREAKER" in r for r in reasons)


def test_personal_scorer_good_match(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp",
        url="https://example.com",
        remote_policy="Remote",
        tech_stack=["Rust", "NixOS", "eBPF"],
        title="Senior Security Architect",
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert score >= 69.0


def test_personal_scorer_no_remote_penalty(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp",
        url="https://example.com",
        remote_policy="Hybrid",
        tech_stack=["Rust", "NixOS"],
        title="Platform Engineer",
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert any("penalty" in r.lower() for r in reasons)


def test_personal_scorer_secondary_skills(mock_profile):
    opp = JobOpportunity(
        company="AcmeCorp",
        url="https://example.com",
        remote_policy="Remote",
        tech_stack=["Python", "Kubernetes"],
        title="Platform Engineer",
    )
    score, reasons = score_opportunity(opp, mock_profile)
    assert any("Secondary" in r for r in reasons)


def test_profile_context_string(mock_profile):
    ctx = mock_profile.as_context_string()
    assert "Test User" in ctx
    assert "Security Architect" in ctx
    assert "Rust" in ctx
    assert "80000" in ctx


@pytest.fixture
def mock_profile():
    from spider_nix.intel.profile import (
        Experience,
        PersonalInfo,
        Preferences,
        Profile,
    )

    return Profile(
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


# ── api_submit tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_greenhouse_api_submit_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "123456"}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await greenhouse_api_submit(
            url="https://boards.greenhouse.io/acme/jobs/123456",
            mapping={"first_name": "Bello", "last_name": "Pina", "email": "test@test.com"},
            cover_letter="Test cover letter.",
        )
    assert result.success is True
    assert result.method == "api"
    assert result.application_id == "123456"


@pytest.mark.asyncio
async def test_greenhouse_bad_url():
    result = await greenhouse_api_submit(
        url="https://careers.example.com/jobs/123",
        mapping={},
        cover_letter="",
    )
    assert result.success is False
    assert "parse" in result.message.lower()


@pytest.mark.asyncio
async def test_lever_api_submit_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        result = await lever_api_submit(
            url="https://jobs.lever.co/acme/550e8400-e29b-41d4-a716-446655440000",
            mapping={"first_name": "Bello", "last_name": "Pina", "email": "test@test.com"},
            cover_letter="Test.",
        )
    assert result.success is True
    assert result.method == "api"


@pytest.mark.asyncio
async def test_lever_bad_url():
    result = await lever_api_submit(
        url="https://example.com/jobs/not-a-lever-url",
        mapping={},
        cover_letter="",
    )
    assert result.success is False


def test_approval_context_fields(mock_profile):
    ctx = ApprovalContext(
        job_url="https://example.com",
        company="Acme",
        role="Security Architect",
        ats_platform="greenhouse",
        score=94.0,
        score_reasons=["Remote ✓", "Rust ✓"],
        field_mapping={"first_name": "Bello", "email": "test@test.com"},
        cover_letter="Cover letter text.",
    )
    assert ctx.score == 94.0
    assert len(ctx.score_reasons) == 2
    assert ctx.ats_platform == "greenhouse"
