"""The non-sensitive slice of the profile that the Matcher, Drafter and
Verifier may see (CLAUDE.md §6): education level, skills, projects,
experience, certifications, achievements, languages.

Never phone, email, address, date of birth, gender or category.
"""

import json
import re

from services.option_match import words


def safe_profile(profile: dict) -> dict:
    p = profile or {}
    degree = (p.get("education") or {}).get("degree") or {}
    return {
        "degree": {k: degree.get(k, "") for k in
                   ("name", "branch", "specialization", "college", "university", "graduation_year", "cgpa", "cgpa_scale")},
        "skills": p.get("skills") or {},
        "projects": p.get("projects") or [],
        "experience": p.get("experience") or [],
        "certifications": p.get("certifications") or [],
        "achievements": p.get("achievements") or [],
        "languages_spoken": p.get("languages_spoken") or [],
    }


def all_skills(facts: dict) -> list[str]:
    """Every skill and project technology, de-duplicated, in profile order."""
    found = [s for group in facts["skills"].values() for s in group]
    found += [t for pr in facts["projects"] for t in pr.get("tech") or []]
    return list(dict.fromkeys(s for s in found if s))


def corpus(facts: dict) -> str:
    """All the facts as one normalised text, for 'is this in the profile?' checks."""
    return f" {words(json.dumps(facts, ensure_ascii=False))} "


def numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))
