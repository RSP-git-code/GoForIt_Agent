"""Coach agent ("Octo"): is this job a fit, what's missing, and how to learn it.

Input: a job description the student pasted (or a company job page read by the
extension) + the profile. Deterministic, no LLM: nothing is invented.

  1. Skills the job asks for (services/learning_resources.py), split into
     required and nice-to-have by the line they appear on.
  2. Which ones the profile already shows (skills, project tech and summaries,
     experience, certifications), with where.
  3. Hard requirements a course can't fix: degree level (M.Tech/MS/PhD), years of
     experience, graduation batch, CGPA / percentage cut-offs. Checked against the
     profile; any failure means "not a fit" (no learning suggestions for those).
  4. A verdict, and for each missing skill: rough effort, free resources, how to show it.
"""

import re

from agents.inbox import ROLE_LEVELS, YEARS_NEEDED, profile_degree_rank, profile_years
from services.learning_resources import SKILLS, videos_and_courses
from services.option_match import words

NICE = re.compile(r"\b(nice to have|good to have|preferred|bonus|a plus|plus point|desirable|added advantage|optional|"
                  r"is a plus|would be great|familiarity with)\b", re.I)
REQUIRED_HEADING = re.compile(r"\b(requirements?|qualifications?|must have|what you need|what we.re looking for|"
                              r"responsibilities|skills required|eligibility)\b", re.I)
BACHELOR = re.compile(r"\b(b\.?\s?tech|b\.?\s?e\b|bachelor'?s?|undergraduate|b\.?\s?sc|bs\b|be/b\.?tech|graduates?)\b", re.I)


def _lines(jd: str) -> list[str]:
    parts = re.split(r"[\n\r]+|(?<=[.;])\s+|\s+[•●▪◦\-*]\s+", jd or "")
    return [p.strip() for p in parts if p and p.strip()]


def _required_and_nice(jd: str) -> list[tuple[str, bool]]:
    """(line, is_nice_to_have) for each line; a "Nice to have:" heading applies to the lines under it."""
    out, nice_section = [], False
    for line in _lines(jd):
        if NICE.search(line) and len(line.split()) <= 6:
            nice_section = True      # a heading like "Good to have:"
        elif REQUIRED_HEADING.search(line) and len(line.split()) <= 6:
            nice_section = False     # a heading like "Requirements:"
        out.append((line, nice_section or bool(NICE.search(line))))
    return out


def _profile_text(profile: dict) -> list[tuple[str, str]]:
    """(where, text) pairs that count as evidence of a skill."""
    out = [("your skills", s) for group in (profile.get("skills") or {}).values() for s in group]
    for p in profile.get("projects") or []:
        title = re.split(r"\s+[-:]\s+", p.get("title", ""))[0]
        out.append((title, " ".join(p.get("tech") or []) + " " + p.get("title", "") + " " + p.get("summary", "")))
    for e in profile.get("experience") or []:
        out.append((f"{e.get('role')} at {e.get('company')}", f"{e.get('role', '')} {e.get('summary', '')}"))
    for c in profile.get("certifications") or []:
        out.append(("certification: " + c.get("name", ""), c.get("name", "")))
    return out


def _mentions(text: str, aliases: list[str]) -> bool:
    t = f" {words(text)} "
    return any(f" {words(a)} " in t for a in aliases)


def _hard_requirements(lines: list[tuple[str, bool]], profile: dict) -> list[dict]:
    """Degree level, years, batch and marks cut-offs on REQUIRED lines, checked against the profile."""
    checks = []
    degree = (profile.get("education") or {}).get("degree") or {}
    for line, nice in lines:
        if nice:
            continue
        low = line.lower()
        # Degree level: "M.Tech/MS required" (but "B.Tech or M.Tech" is fine).
        for rank, name, pattern in sorted(ROLE_LEVELS):  # lowest first: "M.Tech or PhD" means a Master's is enough
            if pattern.search(line) and not BACHELOR.search(line) and profile_degree_rank(profile) < rank:
                checks.append({"requirement": line[:160], "ok": False, "why": f"Asks for a {name} degree"})
                break
        # Years of experience: "2+ years of experience" (only when the line is about experience).
        if re.search(r"\bexperience|\bexp\b", low):
            needed = [int(n) for n in YEARS_NEEDED.findall(line) if int(n) < 30]
            if needed and max(needed) > profile_years(profile):
                checks.append({"requirement": line[:160], "ok": False,
                               "why": f"Asks for {max(needed)}+ years of experience (you have {profile_years(profile)})"})
        # Graduation batch: "2025/2026 batch", "graduating in 2025".
        if re.search(r"\b(batch|pass ?outs?|passing out|graduating|graduated|class of|year of passing)\b", low):
            years = sorted({int(y) for y in re.findall(r"\b(20[2-3]\d)\b", line)})
            mine = degree.get("graduation_year")
            if years and mine and mine.isdigit():
                ranged = len(years) == 2 and re.search(r"\b(to|between|and|-|–)\b|\d\s*[-–]\s*\d", line)
                fits = (years[0] <= int(mine) <= years[-1]) if ranged else int(mine) in years
                checks.append({"requirement": line[:160], "ok": fits,
                               "why": f"Your batch: {mine}" if fits else f"Asks for batch {', '.join(map(str, years))}; yours is {mine}"})
        # CGPA cut-off: "minimum 7.5 CGPA", "CGPA of 8 and above".
        m = re.search(r"(?:cgpa|gpa|cpi)\D{0,25}?(\d{1,2}(?:\.\d+)?)|(\d(?:\.\d+)?)\s*(?:\+|and above|or above)?\s*(?:cgpa|gpa|cpi)", low)
        if m and degree.get("cgpa"):
            cut = float(m.group(1) or m.group(2))
            if 4 <= cut <= 10:
                mine = float(degree["cgpa"])
                checks.append({"requirement": line[:160], "ok": mine >= cut,
                               "why": f"Your CGPA {mine:g} vs cut-off {cut:g}"})
        # Percentage cut-off in academics: "60% throughout", "70% in 10th and 12th".
        m = re.search(r"(\d{2})\s*%\s*(?:and above|or above|throughout|in (?:10th|12th|all))?", low)
        if m and re.search(r"\b(throughout|academic|10th|12th|aggregate|marks|percentage|ssc|hsc)\b", low):
            cut = int(m.group(1))
            edu = profile.get("education") or {}
            marks = [float(x) for x in (edu.get("class_10", {}).get("percentage"), edu.get("class_12", {}).get("percentage"),
                                        degree.get("percentage_equivalent")) if x]
            if marks:
                checks.append({"requirement": line[:160], "ok": min(marks) >= cut,
                               "why": f"Your lowest score {min(marks):g}% vs cut-off {cut}%"})
    return checks


CERT_REQUIRED = re.compile(r"\bcertifi(ed|cation)\b.*\b(mandatory|required|must)\b|\b(mandatory|required|must)\b.*\bcertifi(ed|cation)\b", re.I)


def _certifications_needed(lines: list[tuple[str, bool]], profile: dict) -> list[dict]:
    """Certifications a REQUIRED line calls mandatory ("ITIL Foundation certification is mandatory").
    Unlike a degree, an exam can fix this, so it's reported on its own, not as a reason to skip."""
    held = " ".join(c.get("name", "") for c in profile.get("certifications") or [])
    out = []
    for line, nice_line in lines:
        if nice_line or not CERT_REQUIRED.search(line):
            continue
        for name, info in SKILLS.items():
            if _mentions(line, info["aliases"]) and name not in [c["skill"] for c in out]:
                out.append({"skill": name, "requirement": line[:160], "have": _mentions(held, info["aliases"])})
    return out


def coach(job_text: str, profile: dict, job_title: str = "") -> dict:
    lines = _required_and_nice(f"{job_title}\n{job_text}")
    evidence = _profile_text(profile)
    best_project = next((re.split(r"\s+[-:]\s+", p.get("title", ""))[0] for p in profile.get("projects") or []), "your best project")

    required, nice = {}, {}
    for name, info in SKILLS.items():
        hits = [nice_line for line, nice_line in lines if _mentions(line, info["aliases"])]
        if hits:
            (required if not all(hits) else nice)[name] = info

    matched, missing_required, missing_nice = [], [], []
    for group, target in ((required, missing_required), (nice, missing_nice)):
        for name, info in group.items():
            where = [w for w, text in evidence if _mentions(text, info["aliases"] + [name] + info.get("shown_by", []))]
            if where:
                matched.append({"skill": name, "evidence": ", ".join(dict.fromkeys(where))[:120],
                                "required": group is required})
            else:
                target.append({"skill": name, "effort": info["effort"],
                               # YouTube + Coursera first, then the official docs
                               "resources": [{"title": t, "url": u} for t, u in videos_and_courses(name) + list(info["resources"])],
                               "show": info["show"].replace("{project}", best_project)})

    hard = list({h["why"]: h for h in _hard_requirements(lines, profile)}.values())  # same requirement twice -> once
    certs = _certifications_needed(lines, profile)
    failed = [h for h in hard if not h["ok"]]
    have = sum(1 for m in matched if m["required"])
    fit = round(100 * have / len(required)) if required else None

    if failed:
        verdict, mood = f"Skip: {failed[0]['why']}", "concerned"
    elif fit is None:
        verdict, mood = "Not enough detail in this description to judge the skills", "thinking"
    elif fit >= 75 and len(missing_required) <= 1:
        verdict, mood = "Apply: you match this well" + (f" (brush up {missing_required[0]['skill']})" if missing_required else ""), "happy"
    elif fit >= 50:
        names = ", ".join(m["skill"] for m in missing_required[:2])
        verdict, mood = f"Apply, and brush up {names}", "happy"
    else:
        names = ", ".join(m["skill"] for m in missing_required[:3])
        verdict, mood = f"Stretch: {names} would make you a real fit", "concerned"

    return {"verdict": verdict, "mood": mood, "fit_percent": fit, "matched": matched,
            "missing_required": missing_required, "missing_nice": missing_nice, "hard_requirements": hard,
            "certifications": certs, "skills_asked": len(required),
            # The required lines themselves, so Octo's local AI answers from the job, not from guesses.
            "requirements": [line[:200] for line, nice_line in lines if not nice_line and len(line.split()) > 3][:25]}
