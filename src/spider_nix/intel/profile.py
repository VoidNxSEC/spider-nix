"""User profile loader for job application agent."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PersonalInfo:
    name: str
    email: str
    phone: str
    location: str
    linkedin: str
    github: str
    website: str
    timezone: str


@dataclass
class Experience:
    title: str
    company: str
    start: str
    description: str = ""


@dataclass
class Preferences:
    remote_only: bool
    min_salary_usd: int
    target_roles: list[str]
    dealbreakers: list[str]


@dataclass
class Profile:
    personal: PersonalInfo
    current_experience: Experience
    primary_skills: list[str]
    secondary_skills: list[str]
    languages: list[str]
    preferences: Preferences
    cover_letter_template: str
    llm_api_url: str
    llm_model: str

    def as_context_string(self) -> str:
        """Serialize profile as LLM context string."""
        return f"""
Name: {self.personal.name}
Location: {self.personal.location}
Current Role: {self.current_experience.title} at {self.current_experience.company}
Primary Skills: {", ".join(self.primary_skills)}
Secondary Skills: {", ".join(self.secondary_skills)}
GitHub: {self.personal.github}
Website: {self.personal.website}
LinkedIn: {self.personal.linkedin}
Remote Only: {self.preferences.remote_only}
Min Salary (USD): {self.preferences.min_salary_usd}
Target Roles: {", ".join(self.preferences.target_roles)}
Dealbreakers: {", ".join(self.preferences.dealbreakers)}
        """.strip()


def load_profile(path: Path | str | None = None) -> Profile:
    """
    Load profile from TOML file.

    Looks in:
    1. Explicit path argument
    2. SPIDER_PROFILE env var
    3. ./profile.toml (repo root)
    4. ~/.config/spider-nix/profile.toml
    """
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))

    env_path = os.environ.get("SPIDER_PROFILE")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(Path("profile.toml"))
    candidates.append(Path.home() / ".config" / "spider-nix" / "profile.toml")

    for candidate in candidates:
        if candidate.exists():
            with open(candidate, "rb") as f:
                data = tomllib.load(f)
            return _parse_profile(data)

    raise FileNotFoundError(
        "No profile.toml found. Copy profile.example.toml to profile.toml and fill it in."
    )


def _parse_profile(data: dict) -> Profile:
    p = data["personal"]
    exp = data["experience"]["current"]
    skills = data["skills"]
    prefs = data["preferences"]
    cl = data["cover_letter"]
    llm = data.get("llm", {})

    profile = Profile(
        personal=PersonalInfo(**p),
        current_experience=Experience(**exp),
        primary_skills=skills["primary"],
        secondary_skills=skills.get("secondary", []),
        languages=skills.get("languages", []),
        preferences=Preferences(
            remote_only=prefs.get("remote_only", True),
            min_salary_usd=prefs.get("min_salary_usd", 0),
            target_roles=prefs.get("target_roles", []),
            dealbreakers=prefs.get("dealbreakers", []),
        ),
        cover_letter_template=cl["template"],
        llm_api_url=llm.get("api_url", "http://localhost:9000"),
        llm_model=llm.get("model", "mistral"),
    )

    if "discovery" in data:
        setattr(profile, "_discovery_cfg", data["discovery"])
    if "email" in data:
        setattr(profile, "_email_cfg", data["email"])

    return profile
