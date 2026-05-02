"""Personal job scoring criteria on top of JobAnalyzer."""

from .jobs import JobOpportunity
from .profile import Profile


def score_opportunity(opp: JobOpportunity, profile: Profile) -> tuple[float, list[str]]:
    """
    Score a job opportunity against personal profile.

    Returns (score, reasons[]) where score is 0.0-100.0.
    """
    score = 0.0
    reasons = []
    content = (
        f"{opp.title or ''} {opp.remote_policy or ''} {' '.join(opp.tech_stack)}"
    ).lower()

    # Dealbreaker check — return immediately
    for db in profile.preferences.dealbreakers:
        if db.lower() in content:
            return 0.0, [f"DEALBREAKER: {db}"]

    # Remote
    if opp.remote_policy and "remote" in opp.remote_policy.lower():
        score += 30.0
        reasons.append("Remote ✓")
    elif profile.preferences.remote_only:
        score -= 50.0
        reasons.append("Not remote (penalty)")

    # Primary skills match
    matched_primary = [s for s in profile.primary_skills if s.lower() in content]
    skill_score = len(matched_primary) * 8.0
    score += min(skill_score, 40.0)
    if matched_primary:
        reasons.append(f"Primary skills: {', '.join(matched_primary)}")

    # Secondary skills
    matched_secondary = [s for s in profile.secondary_skills if s.lower() in content]
    score += len(matched_secondary) * 3.0
    if matched_secondary:
        reasons.append(f"Secondary skills: {', '.join(matched_secondary)}")

    # Target role match
    for role in profile.preferences.target_roles:
        if role.lower() in content:
            score += 15.0
            reasons.append(f"Role match: {role}")
            break

    # Salary
    if opp.salary_range:
        reasons.append(f"Salary listed: {opp.salary_range}")
        score += 5.0

    return min(score, 100.0), reasons

