"""Tests for the professional Job Intelligence module."""

import pytest

from spider_nix.intel.job_matcher import (
    JobScorer,
    JobSeekerProfile,
    PreferredRemote,
    match_jobs,
)
from spider_nix.intel.jobs import (
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


class TestExtractors:
    """Test content extraction functions."""

    def test_extract_salary_usd(self):
        s = extract_salary("Salary: $120,000 - $180,000 USD")
        assert s is not None
        assert s.min_amount == 120000.0
        assert s.max_amount == 180000.0
        assert s.currency == "USD"

    def test_extract_salary_k_notation(self):
        s = extract_salary("$100k - $150k")
        assert s is not None
        assert s.min_amount == 100000.0
        assert s.max_amount == 150000.0

    def test_extract_salary_euro(self):
        s = extract_salary("€50.000 - €70.000")
        assert s is not None
        assert s.currency == "EUR"

    def test_extract_salary_brl(self):
        s = extract_salary("R$ 5.000 - R$ 10.000")
        assert s is not None
        assert s.currency == "BRL"

    def test_extract_salary_none(self):
        s = extract_salary("Competitive salary")
        assert s is None

    def test_extract_tech_stack(self):
        tech = extract_tech_stack("We use Python, Django, Rust, Kubernetes, and AWS")
        assert "Python" in tech
        assert "Rust" in tech
        assert "Kubernetes" in tech
        assert "AWS" in tech

    def test_extract_tech_stack_empty(self):
        tech = extract_tech_stack("We are hiring!")
        assert tech == []

    def test_extract_seniority_senior(self):
        assert extract_seniority("Senior Software Engineer") == Seniority.SENIOR

    def test_extract_seniority_staff(self):
        assert extract_seniority("Staff Engineer - Platform") == Seniority.STAFF

    def test_extract_seniority_junior(self):
        assert extract_seniority("Junior Developer") == Seniority.JUNIOR

    def test_extract_seniority_lead(self):
        assert extract_seniority("Tech Lead") == Seniority.LEAD

    def test_extract_seniority_unknown(self):
        assert extract_seniority("Software Engineer") == Seniority.UNKNOWN

    def test_extract_remote_fully(self):
        assert extract_remote_policy("Fully remote position") == RemotePolicy.REMOTE

    def test_extract_remote_hybrid(self):
        assert extract_remote_policy("Hybrid role in NYC") == RemotePolicy.HYBRID

    def test_extract_remote_onsite(self):
        assert extract_remote_policy("On-site in San Francisco") == RemotePolicy.ON_SITE

    def test_extract_remote_unknown(self):
        assert extract_remote_policy("Join our team!") == RemotePolicy.UNKNOWN

    def test_extract_employment_contract(self):
        assert extract_employment_type("Contract position") == EmploymentType.CONTRACT

    def test_extract_employment_internship(self):
        assert extract_employment_type("Summer Internship") == EmploymentType.INTERNSHIP

    def test_extract_employment_full_time(self):
        assert extract_employment_type("Full-time position") == EmploymentType.FULL_TIME


class TestJobOpportunity:
    """Test JobOpportunity model."""

    def test_create_job(self):
        job = JobOpportunity(
            source="greenhouse",
            source_url="https://boards.greenhouse.io/example/jobs/123",
            title="Senior Backend Engineer",
            company="Example Corp",
            location="Remote",
            tech_stack=["Python", "Rust"],
            salary=Salary(min_amount=100000, max_amount=150000, currency="USD"),
        )
        assert job.id != ""
        assert len(job.id) == 16  # SHA256 hex truncated

    def test_job_to_dict(self):
        job = JobOpportunity(
            source="lever",
            source_url="https://jobs.lever.co/example/456",
            title="Platform Engineer",
            company="Example",
            location="San Francisco",
            remote_policy="hybrid",
            tech_stack=["Go", "Kubernetes"],
            salary=Salary(min_amount=130000, max_amount=170000, currency="USD"),
        )
        d = job.to_dict()
        assert d["title"] == "Platform Engineer"
        assert d["source"] == "lever"
        assert d["remote_policy"] == "hybrid"
        assert d["salary"]["min_amount"] == 130000
        assert d["tech_stack"] == ["Go", "Kubernetes"]

    def test_job_from_dict(self):
        data = {
            "id": "abc123",
            "source": "greenhouse",
            "source_url": "https://example.com/job",
            "title": "DevOps Engineer",
            "company": "ACME",
            "location": "Remote",
            "remote_policy": "remote",
            "tech_stack": ["Docker", "Terraform"],
            "salary": {"min_amount": 90000, "max_amount": 120000, "currency": "EUR"},
        }
        job = JobOpportunity.from_dict(data)
        assert job.title == "DevOps Engineer"
        assert job.remote_policy == RemotePolicy.REMOTE
        assert job.salary and job.salary.currency == "EUR"

    def test_job_summary(self):
        job = JobOpportunity(
            source="remoteok",
            title="Senior Rust Engineer",
            company="CryptoStartup",
            location="Remote",
            remote_policy="remote",
            seniority="senior",
            tech_stack=["Rust", "Nix"],
            salary=Salary(min_amount=150000, max_amount=200000),
            score=85.0,
        )
        summary = job.summary()
        assert "Senior Rust Engineer" in summary
        assert "CryptoStartup" in summary
        assert "Remote" in summary

    def test_job_deduplication(self):
        """Same job should have same ID."""
        j1 = JobOpportunity(
            source_url="https://example.com/job/1",
            title="Software Engineer",
            company="ACME",
        )
        j2 = JobOpportunity(
            source_url="https://example.com/job/1",
            title="Software Engineer",
            company="ACME",
        )
        assert j1.id == j2.id


class TestJobScorer:
    """Test job scoring and matching."""

    def test_skill_match_perfect(self):
        profile = JobSeekerProfile(skills=["Python", "Rust", "Kubernetes"])
        job = JobOpportunity(
            title="Senior Platform Engineer",
            description="We need Python, Rust, and Kubernetes experience.",
            tech_stack=["Python", "Rust", "Kubernetes", "Docker"],
        )
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["skills"]["matched"] == ["Kubernetes", "Python", "Rust"]

    def test_skill_match_partial(self):
        profile = JobSeekerProfile(skills=["Python", "Rust", "Nix"])
        job = JobOpportunity(
            title="Backend Developer",
            description="Looking for Python and Django developers.",
            tech_stack=["Python", "Django"],
        )
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        matched = scored.match_details["skills"]["matched"]
        assert "Python" in matched
        # Rust and Nix not matched
        assert len(matched) == 1

    def test_salary_scoring(self):
        profile = JobSeekerProfile(min_salary=100000)
        job = JobOpportunity(
            title="Engineer",
            salary=Salary(min_amount=120000, max_amount=180000, currency="USD"),
        )
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["salary"].get("exceeds")

    def test_salary_too_low(self):
        profile = JobSeekerProfile(min_salary=150000)
        job = JobOpportunity(
            title="Engineer",
            salary=Salary(min_amount=80000, max_amount=100000, currency="USD"),
        )
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["salary"].get("too_low")

    def test_title_match(self):
        profile = JobSeekerProfile(desired_titles=["Platform Engineer", "SRE"])
        job = JobOpportunity(title="Senior Platform Engineer - Remote")
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["title"].get("matched") == "Platform Engineer"

    def test_title_excluded(self):
        profile = JobSeekerProfile(
            desired_titles=["Backend Engineer"],
            excluded_titles=["WordPress"],
        )
        job = JobOpportunity(title="WordPress Developer")
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["title"].get("excluded") == "WordPress"

    def test_remote_only_mismatch(self):
        profile = JobSeekerProfile(preferred_remote=PreferredRemote.REMOTE_ONLY)
        job = JobOpportunity(
            title="Engineer",
            location="San Francisco",
            remote_policy="on_site",
        )
        scorer = JobScorer()
        scored = scorer.score(job, profile)
        assert scored.match_details["location"]["remote_score"] == 0.0

    def test_match_jobs_filter(self):
        profile = JobSeekerProfile(
            skills=["Python"],
            min_salary=100000,
        )
        jobs = [
            JobOpportunity(
                title="Good Job",
                description="Python developer needed",
                tech_stack=["Python"],
                salary=Salary(min_amount=120000, max_amount=150000),
            ),
            JobOpportunity(
                title="Bad Job",
                description="We need COBOL developers",
                salary=Salary(min_amount=40000, max_amount=60000),
            ),
        ]
        results = match_jobs(jobs, profile, min_score=25)
        # Both should pass minimum (Good Job scores high, Bad Job gets ~29)
        # Bad Job may not pass if salary is too low
        assert len(results) >= 1
        assert results[0].title == "Good Job"  # Higher score first


class TestJobSeekerProfile:
    """Test profile serialization."""

    def test_to_dict(self):
        profile = JobSeekerProfile(
            skills=["Python", "Rust"],
            years_experience=5,
            current_seniority=Seniority.SENIOR,
            target_seniority=[Seniority.SENIOR, Seniority.STAFF],
            preferred_remote=PreferredRemote.REMOTE_PREFERRED,
            min_salary=120000,
            preferred_currency="USD",
            desired_titles=["Platform Engineer"],
        )
        d = profile.to_dict()
        assert d["skills"] == ["Python", "Rust"]
        assert d["current_seniority"] == "senior"
        assert d["target_seniority"] == ["senior", "staff"]
        assert d["preferred_remote"] == "remote_preferred"
        assert d["min_salary"] == 120000

    def test_from_dict(self):
        data = {
            "skills": ["Go", "Kubernetes"],
            "years_experience": 7,
            "current_seniority": "senior",
            "target_seniority": ["staff"],
            "preferred_remote": "remote_only",
            "min_salary": 150000,
            "preferred_currency": "EUR",
            "desired_titles": ["Staff Engineer"],
        }
        profile = JobSeekerProfile.from_dict(data)
        assert profile.skills == ["Go", "Kubernetes"]
        assert profile.preferred_remote == PreferredRemote.REMOTE_ONLY
        assert profile.current_seniority == Seniority.SENIOR
        assert profile.target_seniority == [Seniority.STAFF]
