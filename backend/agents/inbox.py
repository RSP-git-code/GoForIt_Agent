"""Inbox agent (Phase 3c): turns placement / job emails into tracker rows.

For each email: is it a job email? -> extract company, role, deadline, apply
link and eligibility rules -> check those rules against the profile -> fit
score from the Matcher (same one the form pipeline uses).

Reading Gmail, writing the .xlsx tracker and creating To Do reminders are
separate steps (services/gmail_reader.py, tracker_xlsx.py, todo_client.py),
so this agent stays pure and testable with sample emails.
"""

import re
from datetime import date, datetime, timedelta

from agents.matcher import match
from app import config
from services.alert_parser import parse_alert
from services.email_extract import check_eligibility, extract
from services.option_match import words
from services.profile_facts import all_skills, safe_profile


def process_email(email: dict, profile: dict) -> dict | None:
    """One email -> one tracker row, or None if it isn't a job/placement email."""
    facts = extract(email)
    if not facts["is_job"]:
        return None
    eligible, problems = check_eligibility(facts["eligibility"], profile)
    fit = match(f"{email.get('subject', '')}\n{email.get('body', '')}", profile)
    links = facts["links"]
    return {
        "email_id": facts["email_id"],
        "received": facts["received"],
        "company": facts["company"] or "",
        "role": facts["role"] or "",
        "deadline": facts["deadline"] or "",
        "apply_link": links[0] if links else "",
        "other_links": links[1:4],
        "eligible": {True: "Yes", False: "No", None: "Not stated"}[eligible],
        "eligibility_notes": "; ".join(problems),
        "fit_score": fit["score"],
        "matched_skills": fit["matched_skills"],
        "subject": email.get("subject", ""),
        "status": "New",
    }


def process_inbox(emails: list[dict], profile: dict) -> list[dict]:
    rows = [process_email(e, profile) for e in emails]
    return [r for r in rows if r]


# ---------- LinkedIn / Indeed job alerts (Phase 3c scope) ----------

# Short forms in job titles and the longer forms used in profiles.
TITLE_SYNONYMS = {
    "ai": ["ai", "aiml", "artificial intelligence", "genai", "gen ai", "generative ai"],
    "ml": ["ml", "aiml", "machine learning"],
    "data science": ["data science", "data scientist"],
    "data analysis": ["data analysis", "data analyst", "analytics"],
    "nlp": ["nlp", "natural language processing"],
    "llm": ["llm", "llms", "large language model"],
    "deep learning": ["deep learning"],
}


def profile_terms(profile: dict) -> dict[str, list[str]]:
    """Terms that make a job title relevant, from the profile only:
    specialization (e.g. "AI and ML"), skills and project technologies."""
    facts = safe_profile(profile)
    text = f" {words(facts['degree'].get('specialization') or '')} {words(' '.join(all_skills(facts)))} "
    terms = {}
    for name, forms in TITLE_SYNONYMS.items():
        if any(f" {words(f)} " in text for f in forms):
            terms[name.upper() if len(name) <= 3 else name.title()] = forms
    for skill in all_skills(facts):
        w = words(skill)
        if w and len(w) > 1 and not any(w in forms for forms in terms.values()):
            terms[skill] = [w]
    return terms


SENIOR = re.compile(r"\b(senior|sr|lead|principal|staff|manager|head|director|architect|vp)\b|\b(ii|iii|iv)\b", re.I)
YEARS_NEEDED = re.compile(r"(\d+)\s*(?:\+|[-–]\s*\d+)?\s*(?:\+\s*)?(?:years?|yrs)", re.I)


def profile_years(profile: dict) -> int:
    """Whole years of work experience in the profile (0 for a fresher)."""
    months = 0
    for job in profile.get("experience") or []:
        start = re.fullmatch(r"(\d{4})-(\d{2})", job.get("start") or "")
        end = re.fullmatch(r"(\d{4})-(\d{2})", job.get("end") or "")
        if start:
            today = date.today()
            ey, em = (int(end.group(1)), int(end.group(2))) if end else (today.year, today.month)
            months += max(0, (ey - int(start.group(1))) * 12 + em - int(start.group(2)))
    return months // 12


# Degree a role is meant for, from the title (or a clear phrase in the snippet).
# Rank matches services/evidence.py: 3 = bachelor's, 4 = master's, 5 = PhD.
ROLE_LEVELS = [
    (5, "PhD", re.compile(r"\b(ph\.?\s?d|doctoral|doctorate|post[- ]?doc\w*)\b", re.I)),
    (4, "Master's", re.compile(r"\b(master'?s|m\.\s?tech|mtech|m\.\s?s\.?|mba|post[- ]?grad\w*|pg students?)\b|\(ms\)", re.I)),
]
SNIPPET_LEVEL = re.compile(r"\b(pursuing|enrolled in|currently in) (a |an |their )?(ph\.?\s?d|master'?s|mba|doctoral)\b"
                           r"|\b(ph\.?\s?d|master'?s|doctoral) (candidates?|students?|program)\b", re.I)


def role_degree(title: str, snippet: str = "") -> tuple[int, str] | None:
    """(rank, name) of the degree a role targets, e.g. (5, "PhD") for "Research Intern (PhD)"."""
    found = SNIPPET_LEVEL.search(snippet)
    for rank, name, pattern in ROLE_LEVELS:
        if pattern.search(title) or (found and pattern.search(found.group(0))):
            return rank, name
    return None


def profile_degree_rank(profile: dict) -> int:
    """3 = bachelor's (default for an engineering student), 4 = master's, 5 = PhD."""
    from services.evidence import _level_of
    name = ((profile.get("education") or {}).get("degree") or {}).get("name") or ""
    level = _level_of(name)
    return int(level) if level and level >= 3 else 3


def title_fit(title: str, profile: dict, snippet: str = "") -> tuple[str, list[str], str]:
    """("High" | "Medium" | "Low", matched terms, reason it's Low or "") for a job.
    Relevance comes from the title; seniority and years asked for can make it Low."""
    t = f" {words(title)} "
    matched = [name for name, forms in profile_terms(profile).items() if any(f" {words(f)} " in t for f in forms)]
    level = "High" if len(matched) >= 2 else "Medium" if matched else "Low"
    have = profile_years(profile)
    why = ""
    needed = role_degree(title, snippet)
    if needed and needed[0] > profile_degree_rank(profile):
        why = f"for {needed[1]} students"
    elif SENIOR.search(title):
        why = "senior role"
    else:
        need = [int(n) for n in YEARS_NEEDED.findall(f"{title} {snippet}")]
        if need and min(need) > have + 1:
            why = f"asks for {min(need)}+ years"
    if why:
        level = "Low"
    return level, matched, why


# Titles that are meant for freshers / students.
FRESHER = re.compile(r"\b(intern|internship|interns|graduate|grad|new grad|trainee|fresher|freshers|junior|jr|"
                     r"entry[- ]?level|associate|apprentice|apprenticeship|campus|20(2[5-9]) (batch|grads?|graduates?|passouts?))\b", re.I)


def experience_signal(title: str, snippet: str, why_low: str) -> str:
    """What the alert says about experience: "Asks N+ years", "Fresher-friendly" or "Not stated: check"."""
    if why_low.startswith("asks for"):
        return why_low.replace("asks for", "Asks")
    if FRESHER.search(title) or re.search(r"\b(freshers?|0[- ]?(to|-)[- ]?[12] (years?|yrs)|no experience required)\b", snippet, re.I):
        return "Fresher-friendly"
    return "Not stated: check"


def companies_needing_experience(rows) -> set[str]:
    """Companies where you marked 2+ roles 'Not eligible' (needs experience) and applied to none."""
    from services.scam_check import company_key
    counts, applied = {}, set()
    for r in rows:
        key = company_key(r.get("company"))
        if str(r.get("status")) == "Not eligible":
            counts[key] = counts.get(key, 0) + 1
        if str(r.get("status")) in ("Applied", "Interview", "Offer"):
            applied.add(key)
    return {k for k, n in counts.items() if n >= 2 and k not in applied}


def posted_date(received: str, signals: list[str]) -> str:
    """When the job was posted, from Indeed's age line ("Just posted", "3 days ago",
    "30+ days ago"). Without one (LinkedIn), the alert's own date is the best estimate."""
    try:
        day = datetime.strptime(received, "%Y-%m-%d").date()
    except ValueError:
        return ""
    for s in signals:
        if re.fullmatch(r"(?i)just posted|today|new", s.strip()):
            return day.isoformat()
        m = re.fullmatch(r"(?i)(\d+)\+?\s*(day|days|hour|hours) ago", s.strip())
        if m:
            back = int(m.group(1)) if m.group(2).lower().startswith("day") else 0
            return (day - timedelta(days=back)).isoformat()
    return day.isoformat()


def next_morning(received: str) -> str:
    """Reminder time: the morning after the alert arrived (config.REMINDER_HOUR)."""
    try:
        day = datetime.strptime(received, "%Y-%m-%d").date()
    except ValueError:
        day = date.today()
    return f"{(day + timedelta(days=1)).isoformat()} {config.REMINDER_HOUR:02d}:00"


def process_alert(mail: dict, profile: dict, scam: set[str] | None = None, needs_exp: set[str] | None = None) -> list[dict]:
    """One LinkedIn/Indeed alert email -> one tracker row per job.
    `scam` = companies you marked as Scam (services/scam_check.py)."""
    from services.scam_check import company_key, red_flag

    rows = []
    for job in parse_alert(mail):
        level, matched, why = title_fit(job["title"], profile, job.get("snippet", ""))
        experience = experience_signal(job["title"], job.get("snippet", ""), why)
        if scam and company_key(job["company"]) in scam:
            level, why = "Low", "company you marked as scam"
        elif needs_exp and company_key(job["company"]) in needs_exp and experience != "Fresher-friendly":
            level, why = "Low", "this company's roles you checked needed experience"
        elif flag := red_flag(job["title"], job.get("snippet", "")):
            level, why = "Low", f"possible scam: {flag}"
        rows.append({
            "job_key": job["job_key"],
            "source": job["source"],
            "received": job["received"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "link": job["link"],
            "fit_score": f"{level} ({why or ', '.join(matched)})" if (why or matched) else level,
            "matched_skills": matched,
            "reminder": next_morning(job["received"]),
            "notes_hint": "; ".join(job["signals"]),
            "posted": posted_date(job["received"], job["signals"]),
            "experience_signal": experience,
        })
    return rows


def process_alerts(mails: list[dict], profile: dict, scam: set[str] | None = None, needs_exp: set[str] | None = None) -> list[dict]:
    """Many alerts -> rows, de-duplicated by job (the same job often appears in several alerts)."""
    by_key = {}
    for mail in mails:
        for row in process_alert(mail, profile, scam, needs_exp):
            by_key.setdefault(row["job_key"], row)
    return list(by_key.values())
