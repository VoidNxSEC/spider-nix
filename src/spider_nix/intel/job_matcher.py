"""
Job Matching Engine — profile/skills-based scoring against job opportunities.

Allows defining a professional profile and scoring jobs against it,
surfacing the best matches based on skill overlap, seniority alignment,
remote policy preference, and salary expectations.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from spider_nix.intel.jobs import (
    TECH_KEYWORDS,
    JobOpportunity,
    RemotePolicy,
    Seniority,
)

# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------


class PreferredRemote(StrEnum):
    REMOTE_ONLY = "remote_only"
    REMOTE_PREFERRED = "remote_preferred"
    HYBRID_OK = "hybrid_ok"
    ANY = "any"


@dataclass
class JobSeekerProfile:
    """
    A job seeker's professional profile.

    Used to match and score job opportunities.
    """

    # Skills
    skills: list[str] = field(default_factory=list)
    # Aliases / keywords to match for each skill
    skill_keywords: dict[str, list[str]] = field(default_factory=dict)

    # Experience
    years_experience: float = 0.0
    current_seniority: Seniority = Seniority.UNKNOWN
    target_seniority: list[Seniority] = field(default_factory=list)

    # Preferences
    preferred_remote: PreferredRemote = PreferredRemote.ANY
    preferred_locations: list[str] = field(default_factory=list)
    excluded_locations: list[str] = field(default_factory=list)

    # Salary
    min_salary: float | None = None
    preferred_currency: str = "USD"

    # Role
    desired_titles: list[str] = field(default_factory=list)
    excluded_titles: list[str] = field(default_factory=list)

    # Companies
    target_companies: list[str] = field(default_factory=list)
    excluded_industries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skills": self.skills,
            "years_experience": self.years_experience,
            "current_seniority": self.current_seniority.value,
            "target_seniority": [s.value for s in self.target_seniority],
            "preferred_remote": self.preferred_remote.value,
            "preferred_locations": self.preferred_locations,
            "min_salary": self.min_salary,
            "preferred_currency": self.preferred_currency,
            "desired_titles": self.desired_titles,
            "target_companies": self.target_companies,
        }

    @classmethod
    def from_dict(cls, data: dict) -> JobSeekerProfile:
        seniority = data.get("current_seniority", "unknown")
        if isinstance(seniority, str):
            try:
                seniority = Seniority(seniority)
            except ValueError:
                seniority = Seniority.UNKNOWN

        target_sen = data.get("target_seniority", [])
        target_seniority = []
        for s in target_sen:
            if isinstance(s, str):
                with contextlib.suppress(ValueError):
                    target_seniority.append(Seniority(s))
            elif isinstance(s, Seniority):
                target_seniority.append(s)

        preferred_remote = data.get("preferred_remote", "any")
        if isinstance(preferred_remote, str):
            try:
                preferred_remote = PreferredRemote(preferred_remote)
            except ValueError:
                preferred_remote = PreferredRemote.ANY

        return cls(
            skills=data.get("skills", []),
            years_experience=float(data.get("years_experience", 0)),
            current_seniority=seniority,  # type: ignore[arg-type]
            target_seniority=target_seniority,
            preferred_remote=preferred_remote,  # type: ignore[arg-type]
            preferred_locations=data.get("preferred_locations", []),
            excluded_locations=data.get("excluded_locations", []),
            min_salary=data.get("min_salary"),
            preferred_currency=data.get("preferred_currency", "USD"),
            desired_titles=data.get("desired_titles", []),
            excluded_titles=data.get("excluded_titles", []),
            target_companies=data.get("target_companies", []),
        )


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class JobScorer:
    """
    Scores job opportunities against a JobSeekerProfile.

    Scoring dimensions (0-100 total):
    - Skill match: 0-40 points
    - Seniority alignment: 0-20 points
    - Remote/location fit: 0-15 points
    - Salary fit: 0-15 points
    - Title/role match: 0-10 points
    """

    MAX_SCORE = 100.0
    WEIGHTS = {
        "skills": 40.0,
        "seniority": 20.0,
        "remote_location": 15.0,
        "salary": 15.0,
        "title_role": 10.0,
    }

    def score(self, job: JobOpportunity, profile: JobSeekerProfile) -> JobOpportunity:
        """
        Score a job against a profile and return the job with score updated.

        The returned job has its .score and .match_details fields populated.
        """
        scores: dict[str, float] = {}
        details: dict[str, Any] = {}

        # 1. Skills match
        skill_score, skill_details = self._score_skills(job, profile)
        scores["skills"] = skill_score
        details["skills"] = skill_details

        # 2. Seniority alignment
        seniority_score, seniority_details = self._score_seniority(job, profile)
        scores["seniority"] = seniority_score
        details["seniority"] = seniority_details

        # 3. Remote / location
        location_score, location_details = self._score_location(job, profile)
        scores["remote_location"] = location_score
        details["location"] = location_details

        # 4. Salary
        salary_score, salary_details = self._score_salary(job, profile)
        scores["salary"] = salary_score
        details["salary"] = salary_details

        # 5. Title / role
        title_score, title_details = self._score_title(job, profile)
        scores["title_role"] = title_score
        details["title"] = title_details

        # Total
        total = sum(scores.values())
        details["total"] = total
        details["breakdown"] = scores

        job.score = total
        job.match_details = details
        return job

    # ---- Skill scoring ----

    def _score_skills(self, job: JobOpportunity, profile: JobSeekerProfile) -> tuple[float, dict]:
        if not profile.skills:
            return self.WEIGHTS["skills"] * 0.5, {"matched": [], "reason": "no profile skills"}

        job_text = (f"{job.title} {job.description} {' '.join(job.tech_stack)}").lower()

        matched: list[str] = []
        partial_matched: list[str] = []

        for skill in profile.skills:
            skill_lower = skill.lower()

            # Direct match in tech stack
            if any(skill_lower == ts.lower() for ts in job.tech_stack):
                matched.append(skill)
                continue

            # Direct match in job text
            if skill_lower in job_text:
                matched.append(skill)
                continue

            # Check keywords
            keywords = profile.skill_keywords.get(skill, TECH_KEYWORDS.get(skill, [skill_lower]))
            for kw in keywords:
                if kw.lower() in job_text:
                    partial_matched.append(skill)
                    break

        # Score
        unique_matches = set(matched) | set(partial_matched)
        if not profile.skills:
            return 0.0, {"matched": [], "partial": []}

        ratio = len(unique_matches) / len(profile.skills)
        # Full matches count more
        full_ratio = len(set(matched)) / len(profile.skills) if profile.skills else 0
        score = self.WEIGHTS["skills"] * (full_ratio * 0.7 + ratio * 0.3)

        return min(score, self.WEIGHTS["skills"]), {
            "matched": sorted(matched),
            "partial": sorted(set(partial_matched) - set(matched)),
            "total_profile_skills": len(profile.skills),
        }

    # ---- Seniority scoring ----

    def _score_seniority(
        self, job: JobOpportunity, profile: JobSeekerProfile
    ) -> tuple[float, dict]:
        job_seniority = job.seniority

        # If job doesn't specify seniority, give partial credit
        if job_seniority == Seniority.UNKNOWN:
            return self.WEIGHTS["seniority"] * 0.4, {"reason": "job seniority unknown"}

        # If profile has target seniorities, check match
        if profile.target_seniority:
            if job_seniority in profile.target_seniority:
                return self.WEIGHTS["seniority"], {"match": job_seniority.value}
            else:
                # Partial credit for adjacent levels
                return self.WEIGHTS["seniority"] * 0.3, {
                    "job": job_seniority.value,
                    "targets": [s.value for s in profile.target_seniority],
                }

        # If no target set, compare to current
        if profile.current_seniority != Seniority.UNKNOWN:
            seniority_levels = list(Seniority)
            try:
                job_idx = seniority_levels.index(job_seniority)
                profile_idx = seniority_levels.index(profile.current_seniority)
                diff = abs(job_idx - profile_idx)

                if diff == 0:
                    return self.WEIGHTS["seniority"], {"match": job_seniority.value}
                elif diff == 1:
                    return self.WEIGHTS["seniority"] * 0.8, {"close": job_seniority.value}
                elif diff == 2:
                    return self.WEIGHTS["seniority"] * 0.4, {"near": job_seniority.value}
                else:
                    return self.WEIGHTS["seniority"] * 0.1, {"far": job_seniority.value}
            except ValueError:
                pass

        return self.WEIGHTS["seniority"] * 0.5, {"reason": "no seniority preference set"}

    # ---- Location scoring ----

    def _score_location(self, job: JobOpportunity, profile: JobSeekerProfile) -> tuple[float, dict]:
        job_remote = job.remote_policy
        job_location = job.location.lower()
        details: dict[str, Any] = {}

        # Exclusion check
        if profile.excluded_locations:
            for excl in profile.excluded_locations:
                if excl.lower() in job_location:
                    return 0.0, {"excluded": excl, "job_location": job.location}

        # Remote policy match
        remote_score = 0.0
        if profile.preferred_remote == PreferredRemote.REMOTE_ONLY:
            if job_remote == RemotePolicy.REMOTE:
                remote_score = 1.0
            elif job_remote == RemotePolicy.UNKNOWN:
                remote_score = 0.3  # might be remote
            else:
                remote_score = 0.0  # not remote
        elif profile.preferred_remote == PreferredRemote.REMOTE_PREFERRED:
            if job_remote == RemotePolicy.REMOTE:
                remote_score = 1.0
            elif job_remote == RemotePolicy.HYBRID:
                remote_score = 0.6
            elif job_remote == RemotePolicy.UNKNOWN:
                remote_score = 0.5
            else:
                remote_score = 0.2
        elif profile.preferred_remote == PreferredRemote.HYBRID_OK:
            if job_remote in (RemotePolicy.REMOTE, RemotePolicy.HYBRID):
                remote_score = 1.0
            elif job_remote == RemotePolicy.UNKNOWN:
                remote_score = 0.6
            else:
                remote_score = 0.4
        else:  # ANY
            remote_score = 0.8  # baseline

        details["remote_score"] = remote_score
        details["job_remote"] = job_remote.value

        # Location match
        location_score = 0.0
        if profile.preferred_locations:
            for pref_loc in profile.preferred_locations:
                if pref_loc.lower() in job_location:
                    location_score = 1.0
                    break
            if location_score == 0.0 and job_remote == RemotePolicy.REMOTE:
                location_score = 0.8  # remote but not preferred location
        else:
            location_score = 1.0  # no preference

        details["location_score"] = location_score

        total = self.WEIGHTS["remote_location"] * (remote_score * 0.6 + location_score * 0.4)
        return min(total, self.WEIGHTS["remote_location"]), details

    # ---- Salary scoring ----

    def _score_salary(self, job: JobOpportunity, profile: JobSeekerProfile) -> tuple[float, dict]:
        if profile.min_salary is None:
            return self.WEIGHTS["salary"], {"reason": "no min salary set"}

        job_salary = job.salary
        if job_salary is None or job_salary.midpoint is None:
            # No salary data — neutral
            return self.WEIGHTS["salary"] * 0.5, {"reason": "no salary data in job"}

        job_midpoint = job_salary.midpoint

        # Currency normalization (rough)
        currency_mult = 1.0
        if job_salary.currency != profile.preferred_currency:
            # Very rough exchange rates (TODO: use an API)
            rates = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "BRL": 0.19, "CAD": 0.73}
            job_mult = rates.get(job_salary.currency, 1.0)
            profile_mult = rates.get(profile.preferred_currency, 1.0)
            currency_mult = job_mult / profile_mult

        job_midpoint_usd = job_midpoint * currency_mult

        if job_midpoint_usd >= profile.min_salary * 1.2:
            return self.WEIGHTS["salary"], {"exceeds": True, "midpoint": job_midpoint_usd}
        elif job_midpoint_usd >= profile.min_salary:
            return self.WEIGHTS["salary"] * 0.85, {"meets": True, "midpoint": job_midpoint_usd}
        elif job_midpoint_usd >= profile.min_salary * 0.7:
            return self.WEIGHTS["salary"] * 0.4, {"low": True, "midpoint": job_midpoint_usd}
        else:
            return self.WEIGHTS["salary"] * 0.1, {"too_low": True, "midpoint": job_midpoint_usd}

    # ---- Title scoring ----

    def _score_title(self, job: JobOpportunity, profile: JobSeekerProfile) -> tuple[float, dict]:
        job_title = job.title.lower()

        # Exclusion check
        for excl in profile.excluded_titles:
            if excl.lower() in job_title:
                return 0.0, {"excluded": excl}

        if not profile.desired_titles:
            return self.WEIGHTS["title_role"] * 0.7, {"reason": "no title preference"}

        for desired in profile.desired_titles:
            if desired.lower() in job_title:
                return self.WEIGHTS["title_role"], {"matched": desired}

        # Partial: check word overlap
        job_words = set(job_title.split())
        for desired in profile.desired_titles:
            desired_words = set(desired.lower().split())
            overlap = job_words & desired_words
            if len(overlap) >= 2:
                return self.WEIGHTS["title_role"] * 0.6, {"partial": desired}

        return self.WEIGHTS["title_role"] * 0.3, {"reason": "no title match"}


# ---------------------------------------------------------------------------
# Bulk matching
# ---------------------------------------------------------------------------


def match_jobs(
    jobs: list[JobOpportunity],
    profile: JobSeekerProfile,
    min_score: float = 30.0,
    top_n: int | None = None,
) -> list[JobOpportunity]:
    """
    Score and filter jobs against a profile.

    Args:
        jobs: List of job opportunities to score
        profile: Job seeker profile to match against
        min_score: Minimum score threshold (0-100)
        top_n: Return top N results (None = all passing threshold)

    Returns:
        Scored and sorted list of jobs (best first)
    """
    scorer = JobScorer()
    scored = [scorer.score(job, profile) for job in jobs]
    filtered = [j for j in scored if j.score >= min_score]
    filtered.sort(key=lambda j: j.score, reverse=True)

    if top_n:
        filtered = filtered[:top_n]

    return filtered
