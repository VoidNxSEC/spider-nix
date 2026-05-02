"""
LLM-powered field mapping and cover letter generation.

Calls ml-ops-api (local) or falls back to direct API call.
Uses the profile + job description to generate:
- A customized cover letter
- A field mapping dict: { detected_field_name: value_from_profile }
- Answers to custom application questions
"""

import json
import httpx
from .profile import Profile


FIELD_MAPPING_PROMPT = """
You are a job application assistant. Given a job description and a candidate profile,
generate a JSON object with:

1. "cover_letter": A 2-paragraph cover letter in the candidate's voice.
   Direct, technical, no fluff. Mention specific tech from the job description.
   Do NOT use phrases like "I am passionate about" or "I am excited to".

2. "field_mapping": A dict mapping common application form field names to values
   from the candidate profile. Common field names include:
   first_name, last_name, email, phone, linkedin_url, github_url, website,
   resume_url, location, years_of_experience, cover_letter, salary_expectation

3. "custom_answers": A dict for any other questions you detect in the job description,
   with concise professional answers from the candidate's perspective.

Return ONLY valid JSON. No markdown, no preamble.

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
{profile_context}
"""


async def generate_mapping(
    job_description: str,
    profile: Profile,
    timeout: float = 60.0,
) -> dict:
    """
    Call local LLM to generate field mapping + cover letter.

    Returns dict with keys: cover_letter, field_mapping, custom_answers
    Falls back to minimal mapping if LLM unavailable.
    """
    prompt = FIELD_MAPPING_PROMPT.format(
        job_description=job_description[:4000],  # truncate for context window
        profile_context=profile.as_context_string(),
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Try OpenAI-compatible endpoint (ml-ops-api / llama.cpp server)
            response = await client.post(
                f"{profile.llm_api_url}/v1/chat/completions",
                json={
                    "model": profile.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]

            # Strip any accidental markdown fences
            content = content.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(content)

    except Exception as e:
        # Fallback: minimal mapping from profile directly
        return _fallback_mapping(profile)


def _fallback_mapping(profile: Profile) -> dict:
    """Minimal mapping when LLM is unavailable."""
    p = profile.personal
    return {
        "cover_letter": profile.cover_letter_template,
        "field_mapping": {
            "first_name": p.name.split()[0],
            "last_name": p.name.split()[-1],
            "full_name": p.name,
            "email": p.email,
            "phone": p.phone,
            "location": p.location,
            "linkedin_url": p.linkedin,
            "github_url": p.github,
            "website": p.website,
        },
        "custom_answers": {},
    }
