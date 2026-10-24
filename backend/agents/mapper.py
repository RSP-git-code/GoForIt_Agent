"""Mapper agent: turns each classified field into a FillAction.

Deterministic, no ML. It looks up the profile value, converts it to what the
field expects (date format, 10-digit phone, CGPA scale, dropdown option), and
flags anything missing or uncertain. It never invents a value (rule 6).
"""

import re
from datetime import date

from services.option_match import PLACEHOLDER, match_option, mentions, words
from services.evidence import answer_yes_no
from services.rules import FREE_TEXT, YES_NO, norm

CHOICE_KINDS = {"select", "radio", "combobox"}


def get_path(obj: dict, path: str):
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def is_empty(v) -> bool:
    return v is None or v == "" or (isinstance(v, list) and not v)


def describe_key(key: str) -> str:
    """'education.class_12.percentage' -> 'class 12 percentage'"""
    return " ".join(key.split(".")[-2:]).replace("_", " ")


def shorten(text: str, limit: int = 40) -> str:
    """Keeps panel messages short (and doesn't echo a whole saved answer)."""
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def hint_text(d: dict) -> str:
    return " ".join(d.get(k) or "" for k in ("label", "placeholder", "helper_text")).lower()


# ---------- value conversions ----------

def format_date(iso: str, d: dict) -> str:
    """YYYY-MM-DD -> what a text box expects. Indian default is DD/MM/YYYY."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m or d.get("kind") == "date":
        return iso
    y, mo, da = m.groups()
    hint = hint_text(d)
    example = EXAMPLE_DATE.search(hint)
    if example:  # the placeholder shows an example date: copy its style
        name = MONTH_NAMES[int(mo) - 1]
        return f"{int(da)} {name if len(example.group(1)) > 3 else name[:3]} {y}"
    if re.search(r"\bmmm\b|\bmon\b|dd[ -]mmm", hint):  # "15 Jun 2004" / "15-Jun-2004"
        sep = "-" if re.search(r"dd-mmm", hint) else " "
        return f"{da}{sep}{MONTH_NAMES[int(mo) - 1][:3]}{sep}{y}"
    ymd = re.search(r"yyyy([/.-])mm\1dd", hint)  # check first: "yyyy/mm/dd" also contains "mm/dd"
    if ymd:
        return f"{y}{ymd.group(1)}{mo}{ymd.group(1)}{da}"
    sep = "-" if re.search(r"dd-mm|mm-dd", hint) else "/"
    if re.search(r"mm[/-]dd", hint):
        return f"{mo}{sep}{da}{sep}{y}"
    return f"{da}{sep}{mo}{sep}{y}"


def country_code(phone: str) -> str | None:
    """'+91 98765 43210' -> '+91'. None if the saved number has no country code."""
    m = re.match(r"\s*(?:\+|00)(\d{1,3})(?=[\s\-()]|\d{10}$)", phone or "")
    return f"+{m.group(1)}" if m else None


def format_phone(phone: str, d: dict) -> str:
    """Indian forms often want exactly 10 digits, without +91. Also when the form
    has a separate country-code dropdown (mapper sets _national_phone)."""
    digits = re.sub(r"\D", "", phone)
    code = country_code(phone)
    national = digits[len(code) - 1:] if code and digits.startswith(code[1:]) else digits
    if d.get("_national_phone") or d.get("max_length") == 10 or re.search(r"10 ?digit|without \+?91|without country code", hint_text(d)):
        return national[-10:] if code == "+91" or not code else national
    return phone


def choose_country_code(code: str, d: dict):
    """Finds '+91' among options like '+91', 'India (+91)', 'IN +91', 'India 91'."""
    digits = code.lstrip("+")
    options = d.get("options") or []
    hits = [o for o in options if re.search(rf"(?<!\d)\+?{digits}(?!\d)", o)]
    with_plus = [o for o in hits if f"+{digits}" in o]
    hits = with_plus or hits
    if len(hits) == 1:
        return hits[0], "filled", ""
    if hits:
        return hits[0], "review", f"Several options use {code}: check the country"
    if not options:
        # Custom dropdowns (e.g. Workday) only show their options once opened.
        country = COUNTRY_BY_CODE.get(code)
        return None, "review", (f"Choose {country} ({code}) from the list" if country else f"Choose country code {code} from the list")
    return None, "missing", f"No option for country code {code}"


COUNTRY_BY_CODE = {"+91": "India", "+1": "United States", "+44": "United Kingdom", "+65": "Singapore",
                   "+971": "United Arab Emirates", "+49": "Germany", "+61": "Australia", "+81": "Japan"}


def convert_cgpa(cgpa: str, scale: str, d: dict):
    """If the field asks for a different scale ("out of 4"), convert proportionally.

    Returns (value, review_reason or "").
    """
    m = re.search(r"(?:out of|scale of|on a|/)\s*(\d+(?:\.\d+)?)", hint_text(d))
    try:
        target, own, value = float(m.group(1)) if m else None, float(scale or 10), float(cgpa)
    except ValueError:
        return cgpa, ""
    if not target or target == own or target not in (4, 5, 10):
        return cgpa, ""
    converted = round(value * target / own, 2)
    return str(converted), f"Converted {cgpa}/{own:g} to {converted}/{target:g} proportionally. Check if the company uses a different formula."


MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]


# "16 June 2014" or "16 Jun 2014" written as an example in a placeholder.
EXAMPLE_DATE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th)? (jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
                          r"sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?),? \d{4}\b")


def format_month_year(month: str, year: str, d: dict):
    """Month "07" + year "2023" -> what the field expects. Returns (value, review_reason)."""
    if d.get("kind") == "month":
        return f"{year}-{month}", ""
    if d.get("kind") == "date":
        # A full date needs a day we don't have; use the 1st and ask for a check.
        return f"{year}-{month}-01", "Day set to the 1st (only month and year are saved)"
    hint = hint_text(d)
    if EXAMPLE_DATE.search(hint) or re.search(r"\bdd\b", hint):
        # The box wants a full date (day included): use the 1st and ask for a check.
        return format_date(f"{year}-{month}-01", d), "Day set to the 1st (only month and year are saved)"
    if re.search(r"\byyyy[/-]mm\b", hint):
        return f"{year}-{month}", ""
    if re.search(r"\b(mon|month name|mmm)\b", hint):
        return f"{MONTH_NAMES[int(month) - 1][:3]} {year}", ""
    sep = "-" if re.search(r"mm-yyyy", hint) else "/"
    return f"{month}{sep}{year}", ""


# Virtual "date" keys built from a month + year pair: key -> (section, month field, year field).
DATE_KEYS = {
    "education.degree.start_date": ("education.degree", "start_month", "start_year"),
    "education.degree.graduation_date": ("education.degree", "graduation_month", "graduation_year"),
    "education.class_12.passing_date": ("education.class_12", "month", "year"),
    "education.class_10.passing_date": ("education.class_10", "month", "year"),
    "education.diploma.passing_date": ("education.diploma", "month", "year"),
    "education.class_12.start_date": ("education.class_12", "start_month", "start_year"),
    "education.class_10.start_date": ("education.class_10", "start_month", "start_year"),
    "education.diploma.start_date": ("education.diploma", "start_month", "start_year"),
}
YEAR_TO_DATE = {
    "education.degree.start_year": "education.degree.start_date",
    "education.degree.graduation_year": "education.degree.graduation_date",
    "education.class_12.year": "education.class_12.passing_date",
    "education.class_10.year": "education.class_10.passing_date",
    "education.diploma.year": "education.diploma.passing_date",
    "education.class_12.start_year": "education.class_12.start_date",
    "education.class_10.start_year": "education.class_10.start_date",
    "education.diploma.start_year": "education.diploma.start_date",
}
MONTH_KEYS = {
    "education.degree.start_month", "education.degree.graduation_month",
    "education.class_12.month", "education.class_10.month", "education.diploma.month",
    "education.class_12.start_month", "education.class_10.start_month", "education.diploma.start_month",
}


# Boxes where each skill becomes its own tag ("Type to Add Skills", "press ENTER
# after each skill", Workday's searchable multi-select). Typing the whole list
# there makes ONE giant tag, so GoForIt only suggests skills for these.
TAG_BOX = re.compile(r"\btype to (add|search)\b|\b(press|click|hit) (the )?enter\b|\bafter each\b|\b(add|select) (your )?skills\b"
                     r"|\bsearch skills\b|\bchoose up to\b|\bselect up to\b")


def is_tag_box(d: dict) -> bool:
    return d.get("kind") == "combobox" or bool(TAG_BOX.search(f"{hint_text(d)} {(d.get('section') or '').lower()}"))


def top_skills(p: dict, limit: int = 12) -> list[str]:
    """A few from each skills group in turn (languages, ML, web...), so the short list stays balanced."""
    groups = [list(g) for g in (p.get("skills") or {}).values() if g]
    picked = []
    while groups and len(picked) < limit:
        for g in groups:
            if g and len(picked) < limit:
                picked.append(g.pop(0))
        groups = [g for g in groups if g]
    return picked


# ---------- profile lookups ----------

def resolve_value(key: str, profile: dict, d: dict):
    """Returns (value, review_reason). value None = not in the profile."""
    p = profile or {}
    personal = p.get("personal") or {}

    # Month/date pickers can't take a bare year ("2023"): use the month + year pair instead.
    if d.get("kind") in ("month", "date") and key in YEAR_TO_DATE:
        key = YEAR_TO_DATE[key]

    if key == "education.marking_scheme":
        return marking_scheme(p, d)
    if key == "education.result_status":
        return result_status(p, d)
    if key == "personal.full_name":
        full = personal.get("full_name") or " ".join(
            x for x in (personal.get("first_name"), personal.get("middle_name"), personal.get("last_name")) if x
        )
        return (full or None), ""
    if key == "personal.phone_country_code":
        return country_code(personal.get("phone") or ""), ""
    if key == "personal.phone_type":
        # Indian mobile numbers are 10 digits starting with 6-9.
        digits = re.sub(r"\D", "", personal.get("phone") or "")
        if re.fullmatch(r"(91)?[6-9]\d{9}", digits):
            return "Mobile", ""
        return None, ("Phone type: check which kind of number you saved" if digits else "")
    if key in ("personal.phone", "personal.alternate_phone"):
        phone = get_path(p, key)
        return (format_phone(phone, d) if phone else None), ""
    if key == "personal.date_of_birth":
        dob = get_path(p, key)
        if not dob:
            return None, ""
        # Split boxes ("Date of Birth Day / Month / Year", Oracle Cloud): only that part.
        part = re.search(r"\b(day|month|year)\s*\*?\s*$", (d.get("label") or "").lower())
        m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", dob)
        if part and m:
            y, mo, da = m.groups()
            unit = part.group(1)
            if unit == "day":
                return str(int(da)), ""
            if unit == "month":
                return MONTH_NAMES[int(mo) - 1], ""  # dropdowns also match "12" / "Dec" via synonyms
            return y, ""
        return format_date(dob, d), ""
    if key == "education.degree.cgpa":
        degree = get_path(p, "education.degree") or {}
        if not degree.get("cgpa"):
            return None, ""
        return convert_cgpa(str(degree["cgpa"]), str(degree.get("cgpa_scale") or "10"), d)
    if key in DATE_KEYS:
        section, month_key, year_key = DATE_KEYS[key]
        level = get_path(p, section) or {}
        month, year = level.get(month_key), level.get(year_key)
        if not month or not year:
            return None, ""
        return format_month_year(str(month).zfill(2), str(year), d)
    if key in MONTH_KEYS:
        month = get_path(p, key)
        if not month:
            return None, ""
        # Text boxes get the name ("July"); dropdowns match it via synonyms (Jul, 07).
        return MONTH_NAMES[int(month) - 1], ""
    if key == "preferences.willing_to_relocate":
        return answer_relocation(p, d)
    if key == "experience.total_years":
        return total_experience(p)
    if key == "education.summary":
        return education_summary(p)
    if key in ("education.entry.from", "education.entry.to"):
        degree = get_path(p, "education.degree") or {}
        prefix = "start" if key.endswith("from") else "graduation"
        year, month = degree.get(f"{prefix}_year"), degree.get(f"{prefix}_month")
        if not year:
            return None, ""
        note = f"Assumed this education entry is your {degree.get('name') or 'degree'}: check"
        if d.get("kind") in ("month", "date") or re.search(r"\bmm\b|month", hint_text(d)):
            if not month:
                return None, f"Add your {prefix} month in your profile ({note.lower()})"
            value, extra = format_month_year(str(month).zfill(2), str(year), d)
            return value, f"{note}. {extra}".strip(". ") if extra else note
        return str(year), note
    if key in ("education.entrance_exams.jee_main", "education.entrance_exams.jee_advanced"):
        exams = (p.get("education") or {}).get("entrance_exams") or {}
        name = key.split(".")[-1]
        pct, rank = str(exams.get(f"{name}_percentile") or "").strip(), str(exams.get(f"{name}_rank") or "").strip()
        if pct.upper() == "NA" or rank.upper() == "NA":
            return "NA", ""
        parts = ([f"{pct} percentile"] if pct else []) + ([f"Rank {rank}"] if rank else [])
        return (", ".join(parts) or None), ""
    if key == "subject_marks":
        subject = re.search(r"\b(maths?|mathematics)\b", hint_text(d))
        value = get_path(p, "education.class_12.math_percentage") if subject else None
        return (str(value) if value else None), ""
    if key == "education.degree.status":
        degree = get_path(p, "education.degree") or {}
        try:
            y, m = int(degree.get("graduation_year")), int(degree.get("graduation_month") or 6)
        except (TypeError, ValueError):
            return None, ""
        today = date.today()
        return ("Completed" if (y, m) <= (today.year, today.month) else "In Progress"), ""
    if key == "experience.summary":
        jobs = p.get("experience") or []
        if not jobs:
            return "No prior internship or work experience.", "From your profile (no experience entries): check"
        lines = [f"{j.get('role', '')} at {j.get('company', '')} ({j.get('start', '')} to {j.get('end') or 'present'})"
                 + (f": {j['summary']}" if j.get("summary") else "") for j in jobs]
        return "\n".join(lines), "From your experience entries: check"
    if key == "links.portfolio" and not get_path(p, key):
        github = get_path(p, "links.github")
        return (github or None), ("No portfolio saved, so your GitHub was used" if github else "")
    if key == "skills.all" and is_tag_box(d):
        top = top_skills(p)
        if not top:
            return None, ""
        return None, "Tag box (each skill is added with Enter), so GoForIt didn't type here. Add these one at a time: " + ", ".join(top)
    if key == "skills.all":
        skills = [s for group in (p.get("skills") or {}).values() for s in group]
        limit = re.search(r"\b(?:up to|upto|max(?:imum)?|top|at most)\s*(\d+)\b", hint_text(d))
        if limit:
            skills = skills[: int(limit.group(1))]
        return (skills or None), "Check the skills listed fit this question"
    if key == "certifications.all":
        names = [f"{c['name']} ({c['issuer']})" if c.get("issuer") else c.get("name", "") for c in p.get("certifications") or []]
        # One per line in a big box; a one-line box drops line breaks (names ran together), so "; " there.
        sep = "\n" if d.get("kind") == "textarea" else "; "
        return (sep.join(n for n in names if n) or None), "Check this list"
    if key == "projects.all":
        titles = [pr.get("title") for pr in p.get("projects") or [] if pr.get("title")]
        return (", ".join(titles) or None), "Check this list"
    if key == "education.degree.branch" and d.get("kind") == "combobox" and not d.get("options"):
        # A searchable picker (Workday "Field of Study"): its list says "Computer Science" or
        # "Computer Engineering", rarely your exact wording, so the extension tries these in order.
        degree = get_path(p, "education.degree") or {}
        branch = str(degree.get("branch") or "").strip()
        if branch:
            short = re.sub(r"\s*(and|&)\s*engineering$|\s+engineering$", "", branch, flags=re.I).strip()
            tries = [branch, short, f"{short} Engineering" if short != branch else "", degree.get("branch_full") or ""]
            tries = list(dict.fromkeys(t for t in tries if t))
            return (tries if len(tries) > 1 else branch), "Picked from the site's list: check it's your field"
    if key in ("education.degree.branch", "education.degree.specialization") and d.get("kind") not in CHOICE_KINDS \
            and d.get("kind") != "checkbox":
        # Text boxes get your branch the way you write it on forms. (Dropdowns still
        # match options like "CSE (AI and ML)" from branch + specialization.)
        degree = get_path(p, "education.degree") or {}
        asks_branch = key.endswith("branch") or re.search(r"\bbranch\b", hint_text(d))
        if asks_branch and degree.get("branch_full"):
            return degree["branch_full"], ""
        if asks_branch and degree.get("branch") and degree.get("specialization") \
                and re.search(r"speciali[sz]ation", hint_text(d)):
            return f"{degree['branch']} with Specialization in {degree['specialization']}", ""
    if key == "achievements":
        return pick_achievements(p, d)
    if key in ("publications", "memberships"):
        items = [str(x).strip() for x in p.get(key) or [] if str(x).strip()]
        if not items:
            where = ("Publications (e.g. \"Title (under review at …)\")" if key == "publications"
                     else "Professional bodies / club memberships")
            return None, f"Nothing saved yet: add it under Edit profile → {where}, or write it yourself"
        return "\n".join(items), "From your profile: check it"
    if key == "languages_spoken" and d.get("kind") in CHOICE_KINDS:
        # One "Language" dropdown (more need "Add language"): your first language that's an option.
        names = [language_and_level(x)[0] for x in p.get("languages_spoken") or []]
        pick = next((n for n in names if match_option(n, d.get("options") or [])), None)
        if not pick:
            return None, ("None of your languages is in this list" if names else "")
        more = [n for n in names if n != pick]
        return pick, (f"Click \"Add\" yourself for more ({', '.join(more)}), then Fill again" if more else "")
    if key == "languages.proficiency":
        return language_proficiency(p, d)
    if key == "skills.experience":
        return skill_experience(p, d)
    if key in ("relatives.at_company", "relatives.details"):
        return relatives_answer(key, p, d)
    if key.startswith("diversity."):
        return diversity_answer(key, p, d)
    if key == "personal.country":
        saved = personal.get("country")
        if saved:
            return saved, ""
        if words(personal.get("nationality") or "") in ("indian", "india"):
            return "India", "From your nationality (Indian): check it's where you live"
        return None, ""
    if key == "languages_spoken" and re.search(r"\bforeign\b", hint_text(d)):
        # "Additional Foreign Language known (e.g. French)": not English or Indian languages.
        names = [language_and_level(x)[0] for x in p.get("languages_spoken") or []]
        foreign = [n for n in names if words(n) not in INDIAN_LANGUAGES]
        return (", ".join(foreign) or None), ("" if foreign else "No foreign language in your profile")
    if key == "links.coding_platform":
        return choose_platform(p, d)
    if key == "links.coding_profile":
        return coding_profile_link(p, d)
    if key in ("experience.current_company", "experience.current_title"):
        jobs = p.get("experience") or []
        current = next((e for e in jobs if not e.get("end") or re.search(r"present|current", e["end"], re.I)), None)
        if current:
            return current.get("company" if key.endswith("company") else "role") or None, ""
        if not jobs:  # a student with no work experience
            return ("NA", "You have no work experience saved") if key.endswith("company") else \
                ("Student", "You have no work experience saved")
        return None, ""
    if key == "preferences.available_from":
        return available_from(p, d)

    if key == "standard_answers.about_me" and not get_path(p, key):
        written = summary_from_profile(p)
        return (written or None), "Written from your profile (no saved About me): read and edit it"

    value = get_path(p, key)
    if is_empty(value):
        return None, ""
    if isinstance(value, (int, float)):
        value = str(value)
    review = "Saved answer: check it fits this question" if key.startswith("standard_answers.") else ""
    return value, review


# ---------- a summary when "About me" isn't saved ----------

def summary_from_profile(profile: dict) -> str:
    """2-3 sentences built only from profile facts: degree, top skills, best project."""
    from agents.drafter import _student_line
    from services.profile_facts import all_skills, safe_profile

    facts = safe_profile(profile)
    parts = [_student_line(facts)]
    skills = all_skills(facts)[:6]
    if skills:
        parts.append(f"Skilled in {', '.join(skills)}.")
    projects = [pr for pr in facts["projects"] if pr.get("title")]
    if projects:
        first = re.match(r"(.+?[.!?])(\s|$)", (projects[0].get("summary") or "").strip())
        what = first.group(1) if first else (projects[0].get("summary") or "").strip()
        parts.append(f"Projects include {projects[0]['title']}" + (f": {what[:1].lower()}{what[1:]}" if what else "."))
    return " ".join(p for p in parts if p).strip()


# ---------- relocation, experience, education summary ----------

# ---------- relatives at the company ----------

def asked_company(label: str) -> str:
    """'Do you have any relatives working within HSBC group?' -> 'hsbc'. '' if the question names none."""
    m = re.search(r"\b(?:within|with|at|in|for|of|by)\s+(?:the\s+)?([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,3})", label or "")
    name = words(m.group(1)) if m else ""
    name = re.sub(r"\b(group|limited|ltd|inc|plc|llp|pvt|private|company|corporation|corp|india|global)\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return "" if name in ("", "our", "us", "this", "the", "any") else name


def relatives_answer(key: str, p: dict, d: dict):
    """From profile["relatives"]: Yes/No for "relatives working at X?", and the details for the follow-up."""
    relatives = [r for r in p.get("relatives") or [] if (r.get("company") or "").strip()]
    company = asked_company(d.get("label") or "")
    if company:
        matches = [r for r in relatives if company in words(r["company"]) or words(r["company"]) in company]
    else:  # "our organisation": can't tell which company, so only a list to check against
        matches = []
    where = ", ".join(r["company"] for r in relatives) or "none saved"
    if key == "relatives.at_company":
        if matches:
            return "Yes", f"Your relative works at {matches[0]['company']}"
        if not company and relatives:
            return None, f"Check: your saved relatives work at {where}"
        return "No", (f"Your saved relatives work at {where}, not here" if relatives
                      else "No relatives saved in your profile: check")
    # The details follow-up.
    if not matches:
        if not company and relatives:
            return None, f"Check: your saved relatives work at {where}"
        return "Not applicable", "No relative of yours works here (from your profile): check"
    r = matches[0]
    who = r.get("name") or "My relative"
    parts = [f"{who}" + (f" ({r['relation']})" if r.get("relation") else "")]
    parts += [x for x in (r.get("job_title"), r.get("department"), r.get("location")) if x]
    return ", ".join(parts), "From Relatives in your profile: check"


# ---------- diversity answers (optional) ----------

def _ethnicity_choices(saved: str) -> list[str]:
    """Your wording first, then broader ones forms use: "Asian - Indian Subcontinent" -> + Indian, South Asian, Asian."""
    choices = [saved]
    t = words(saved)
    if "indian" in t or "india" in t:
        choices += ["Asian - Indian Subcontinent", "Indian", "Asian Indian", "South Asian", "Asian or Asian British - Indian",
                    "Asian"]
    elif "asian" in t:
        choices += ["Asian"]
    return list(dict.fromkeys(choices))


def diversity_answer(key: str, p: dict, d: dict):
    """From profile["diversity"]. Empty = left for you (these are your choice to share)."""
    saved = str(((p.get("diversity") or {}).get(key.split(".", 1)[1])) or "").strip()
    if not saved:
        return None, "Your choice (optional: save it under Diversity answers in your profile)"
    options = [o for o in d.get("options") or [] if not PLACEHOLDER.search(o.strip().lower())]
    choices = _ethnicity_choices(saved) if key == "diversity.ethnicity" else [saved]
    if key == "diversity.veteran":
        choices += ["I am not a protected veteran", "Not a veteran", "No"]
    if options:
        for i, c in enumerate(choices):
            m = match_option(c, options)
            if m:
                return m.option, ("" if i == 0 and m.exact else f'Closest option to your "{saved}": check')
        return None, f'No option matches your "{saved}": pick yourself'
    # A site dropdown whose options appear only when opened: send the alternatives in order.
    return (choices if len(choices) > 1 and d.get("kind") == "combobox" else saved), ""


# ---------- "experience in X" from projects and skills ----------

# What a subject can appear as in a profile ("AI/ML" shows up as scikit-learn, PyTorch, RAG...).
SUBJECT_ALIASES = {
    "ai ml": ["machine learning", "deep learning", "scikit learn", "tensorflow", "keras", "pytorch", "rag", "langchain",
              "generative ai", "llm", "reinforcement learning", "nlp"],
    "machine learning": ["machine learning", "scikit learn", "tensorflow", "keras", "pytorch", "logistic regression",
                         "random forest", "lstm", "smote"],
    "ml": ["machine learning", "scikit learn", "tensorflow", "keras", "pytorch"],
    "ai": ["machine learning", "deep learning", "generative ai", "llm", "rag", "langchain", "pytorch", "tensorflow"],
    "llm": ["llm", "langchain", "rag", "gemini", "watsonx", "openai", "generative ai", "prompt engineering"],
    "deep learning": ["deep learning", "tensorflow", "keras", "pytorch", "lstm", "rnn", "cnn"],
    "sql": ["sql", "postgresql", "sqlite", "mysql"],
    "cloud": ["aws", "azure", "gcp", "cloud"],
}


def _subject_terms(label: str) -> tuple[str, list[str]]:
    """'Hands on experience in LLM APIs' -> ("LLM APIs", [llm aliases])."""
    m = re.search(r"experience (?:you (?:have|hold) )?(?:in|with|of|using|on)\s+(.+?)\s*[?*.:]*\s*$", label, re.I)
    subject = (m.group(1) if m else "").strip()
    key = words(subject)
    key = re.sub(r"\b(apis?|frameworks?|tools?|libraries|library|technolog(y|ies)|programming|language|development)\b", " ", key)
    key = re.sub(r"\s+", " ", key).strip()
    return subject, SUBJECT_ALIASES.get(key, [key] if key else [])


def skill_experience(p: dict, d: dict):
    """"Hands on experience in Python?" -> which projects used it (never invented). None if nowhere in the profile."""
    subject, aliases = _subject_terms(d.get("label") or "")
    if not aliases:
        return None, ""

    def mentions(text: str) -> bool:
        t = f" {words(text)} "
        return any(f" {words(a)} " in t for a in aliases)

    projects = [pr for pr in p.get("projects") or []
                if mentions(" ".join(pr.get("tech") or [])) or mentions(f"{pr.get('title', '')} {pr.get('summary', '')}")]
    in_skills = [s for group in (p.get("skills") or {}).values() for s in group if mentions(s)]
    jobs = [j for j in p.get("experience") or [] if mentions(f"{j.get('role', '')} {j.get('summary', '')}")]
    if not projects and not in_skills and not jobs:
        return None, f"{subject} isn't in your profile: answer yourself"
    parts = []
    if jobs:
        parts.append("; ".join(f"{j.get('role')} at {j.get('company')}" for j in jobs[:2]))
    elif re.search(r"\bhow much\b", d.get("label") or "", re.I):
        parts.append("No industry experience yet")
    if projects:
        names = []
        for pr in projects[:3]:
            used = [t for t in pr.get("tech") or [] if mentions(t)]
            short = re.split(r"\s+[-:]\s+", pr.get("title", ""))[0]  # "Smart Resume Scanner - RAG-based..." -> "Smart Resume Scanner"
            names.append(f"{short} ({', '.join(used)})" if used else short)
        parts.append(("hands-on through my projects: " if parts else "Yes, hands-on through my projects: ") + "; ".join(names))
    elif in_skills:
        parts.append(f"Yes, {', '.join(in_skills[:4])} {'is' if len(in_skills) == 1 else 'are'} in my skills")
    text = "; ".join(parts) + "."
    text = text[0].upper() + text[1:]
    limit = d.get("max_length")
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(";", 1)[0] + "."
    return text, "From your projects and skills: check"


# ---------- languages and proficiency ----------

def language_and_level(entry: str) -> tuple[str, str]:
    """"English (Fluent)", "English - Fluent", "English: Native" -> ("English", "Fluent"). No level -> ("English", "")."""
    m = re.match(r"\s*([^(:\-]+?)\s*(?:\(([^)]*)\)|[:\-]\s*(.+))?\s*$", str(entry))
    if not m:
        return str(entry).strip(), ""
    return m.group(1).strip(), (m.group(2) or m.group(3) or "").strip()


# Your level -> the words forms use for it (first match among the options wins).
LEVEL_WORDS = {
    "native": ["native", "bilingual", "mother tongue", "first language"],
    "fluent": ["fluent", "full professional", "professional working", "advanced", "proficient", "expert"],
    "advanced": ["advanced", "fluent", "full professional", "proficient"],
    "intermediate": ["intermediate", "conversational", "limited working", "working"],
    "basic": ["basic", "beginner", "elementary", "limited"],
}


def language_proficiency(p: dict, d: dict):
    """The "Proficiency" dropdown next to a "Language" one: the level saved for that language,
    written like "English (Fluent)" in Languages known. d["_language"] is the language picked just before."""
    language = str(d.get("_language") or "")
    entries = {words(language_and_level(x)[0]): language_and_level(x)[1] for x in p.get("languages_spoken") or []}
    level = entries.get(words(language), "")
    if not language:
        return None, "Pick the proficiency yourself"
    if not level:
        return None, f'Pick your {language} proficiency (save it in your profile as "{language} (Fluent)" to fill it next time)'
    options = d.get("options") or []
    if not options:
        return level, ""
    for word in LEVEL_WORDS.get(words(level), [words(level)]):
        hit = next((o for o in options if word in words(o)), None)
        if hit:
            return hit, ""
    return None, f'No option matches your {language} level "{level}"'


# English and the languages of India: not "foreign" on an Indian form.
INDIAN_LANGUAGES = {"english", "hindi", "marathi", "telugu", "tamil", "kannada", "malayalam", "bengali", "bangla",
                    "gujarati", "punjabi", "urdu", "odia", "oriya", "assamese", "konkani", "sanskrit", "kashmiri",
                    "sindhi", "nepali", "manipuri", "maithili", "dogri", "bodo", "santali", "tulu"}

# ---------- coding platforms and achievements ----------

# Platform name -> how it's written in labels, options and saved links.
PLATFORMS = [("LeetCode", r"leet ?code"), ("CodeChef", r"code ?chef"), ("Codeforces", r"code ?forces"),
             ("HackerRank", r"hacker ?rank"), ("GeeksforGeeks", r"geeks ?for ?geeks|\bgfg\b"),
             ("HackerEarth", r"hacker ?earth"), ("GitHub", r"git ?hub")]


def saved_platform_links(p: dict) -> dict[str, str]:
    """{"LeetCode": url, "CodeChef": url, ...} from links.leetcode/github and lines like
    "CodeChef:https://www.codechef.com/users/me" in links.other."""
    links = p.get("links") or {}
    entries = [links.get("leetcode") or "", links.get("github") or ""] + [str(x) for x in links.get("other") or []]
    found = {}
    for entry in entries:
        url = re.search(r"https?://\S+", entry)
        if not url:
            continue
        for name, pattern in PLATFORMS:
            if name not in found and re.search(pattern, entry, re.I):
                found[name] = url.group(0)
    return found


def choose_platform(p: dict, d: dict):
    """'Coding Platform' choice: the options you have a saved profile on (page order; the
    first one for single-choice). The link box after it then uses that platform."""
    saved = saved_platform_links(p)
    names = [n for n in saved if n != "GitHub"]
    if not names:
        return None, "No coding profile saved (add LeetCode etc. in Edit profile)"
    options = [o for o in d.get("options") or [] if not PLACEHOLDER.search(o.strip().lower())]
    if not options:
        return ", ".join(names), "Your saved coding profiles"
    matching = [o for o in options if any(re.search(pat, o, re.I) for n, pat in PLATFORMS if n in names)]
    if not matching:
        return None, f"None of these options match your saved profiles ({', '.join(names)})"
    if d.get("kind") == "checkbox":
        return matching, "Platforms you have a saved profile on"
    return matching[0], (f"You have profiles on {', '.join(names)}: picked the first listed" if len(matching) > 1 else "")


def coding_profile_link(p: dict, d: dict):
    """A profile link box: the platform picked just above on the page (d["_platform"]),
    else your first saved coding profile."""
    saved = saved_platform_links(p)
    platform = str(d.get("_platform") or "")
    for name, pattern in PLATFORMS:
        if platform and re.search(pattern, platform, re.I) and name in saved:
            return saved[name], f"Your {name} profile (the platform picked above)"
    for name, url in saved.items():
        if name != "GitHub":
            return url, f"Your {name} profile"
    return None, ""


# Words that mark an achievement as a hackathon / competition, and the result words in it.
COMPETITION = r"hackathon|hacktoberfest|competition|contest|olympiad|ctf|challenge|coding round|codeathon|ideathon"
RESULT = re.compile(r"\b(winner|won|first|1st|second|2nd|third|3rd|runner[- ]?up|finalist|semi[- ]?finalist|"
                    r"top \d+|rank \d+|participant|participated|honou?rable mention|special mention)\b", re.I)


def pick_achievements(p: dict, d: dict):
    """Achievements that fit the question. A one-line box gets ONE item (or just its
    result, for "Achievement - Example (Finalist)"), never the whole list."""
    items = [str(x) for x in p.get("achievements") or [] if str(x).strip()]
    if not items:
        return None, ""
    label = (d.get("label") or "").lower()
    question = re.sub(r"\bexample\b.*$|\(.*?\)", " ", label)  # "Example (Smart India Hackathon)" is not the topic
    if re.search(COMPETITION, question):
        items = [i for i in items if re.search(COMPETITION, i, re.I)]
        if not items:
            return None, "None of your saved achievements is a hackathon or competition"
    if d.get("kind") == "textarea":
        return "\n".join(items), "Check this list"
    first = items[0]
    asks_result = re.search(r"\b(achievement|result|position|rank|outcome|award)\b", question) and \
        re.search(COMPETITION, question)
    if asks_result:
        result = RESULT.search(first)
        if result:
            word = result.group(1).lower()
            return {"won": "Winner", "participated": "Participant"}.get(word, word.title()), f"From: {first}"
        return first, "Check: write just the result (e.g. Finalist)"
    reason = "Picked the most relevant achievement" + (f" ({len(items)} match)" if len(items) > 1 else "")
    return first, reason


def option_days(option: str) -> float | None:
    """How many days from now an availability option means: "Immediately" 0, "Within 2 weeks" 14, "30-60 days" 60."""
    t = option.lower()
    if re.search(r"\+|\b(more than|above|over|later than|after)\b", t):
        return float("inf")  # "60+ days", "More than 3 months": only when nothing shorter fits
    if re.search(r"\bimmediate|\bright away|\basap\b|\bcouple of weeks\b", t):
        return 14 if "couple of weeks" in t else 0
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums:
        return None
    n = max(nums)
    if re.search(r"\bweeks?\b", t):
        return n * 7
    if re.search(r"\bmonths?\b", t):
        return n * 30
    if re.search(r"\bdays?\b", t):
        return n
    return None


def available_from(p: dict, d: dict):
    """'When can you start?' from preferences.available_from (a date) or, if empty, notice period 0."""
    prefs = p.get("preferences") or {}
    saved = str(prefs.get("available_from") or "").strip()
    today = date.today()
    try:
        start = date.fromisoformat(saved) if saved else None
    except ValueError:
        start = None
    if start is None:
        if str(prefs.get("notice_period") or "").strip().lower() in ("0", "immediate", "immediately", "0 days"):
            start = today
        else:
            return None, ""
    # Answers go by month: a saved 23 Nov reads "November 2026" until 31 Oct,
    # and from 1 Nov it's "Immediately".
    start = start.replace(day=1)
    days = (start - today).days
    options = [o for o in d.get("options") or [] if o.strip() and not PLACEHOLDER.search(o)]
    if options:
        if days <= 0:
            pick = next((o for o in options if option_days(o) == 0), None)
        else:
            # Month-name options ("November", "Nov 2026"): the month you can start.
            month = MONTH_NAMES[start.month - 1].lower()
            pick = next((o for o in options if re.search(rf"\b{month[:3]}", o.lower())), None)
            if not pick:
                # The shortest option that still covers the wait; ties keep the page's order.
                fits = sorted((option_days(o), i) for i, o in enumerate(options) if option_days(o) is not None and option_days(o) >= days)
                pick = options[fits[0][1]] if fits else None
        if not pick:
            return None, f"Pick the option that fits starting {start:%B %Y}" if days > 0 else "Pick the earliest option"
        return pick, (f"You can join from {start:%B %Y}" if days > 0 else "")
    # Boxes that need an exact date get the 1st of that month (or today once it has come).
    exact = max(start, today)
    if d.get("kind") == "date":
        return exact.isoformat(), ""
    if d.get("kind") == "month":
        return f"{exact:%Y-%m}", ""
    if re.search(r"\bdd\b", hint_text(d)):  # DD/MM/YYYY
        return format_date(exact.isoformat(), d), ""
    m = re.search(r"\bmm\s*([/-])\s*yy", hint_text(d))  # MM/YYYY (HCLTech's "available to join")
    if m:
        return f"{start:%m}{m.group(1)}{start:%Y}" if days > 0 else f"{exact:%m}{m.group(1)}{exact:%Y}", ""
    if days <= 0:
        return "Immediately", ""
    if re.search(r"\bhow soon\b|\bhow long\b", hint_text(d)):
        return f"From {start:%B %Y} (in about {max(1, round(days / 7))} weeks)", ""
    return f"{start:%B %Y}", ""


def answer_relocation(profile: dict, d: dict):
    """'Will you relocate to Bengaluru?' -> from preferred locations, then the saved answer.
    Returns (value, review_reason) like resolve_value; value None = flag it."""
    prefs = profile.get("preferences") or {}
    places = [words(x) for x in prefs.get("preferred_locations") or []]
    city = words((profile.get("personal") or {}).get("current_city") or "")
    asked = words(f"{d.get('label', '')} {d.get('helper_text', '')}")
    hits = [p for p in places + [city] if p and f" {p} " in f" {asked} "]
    if hits:
        where = "your current city" if hits[0] == city else "in your preferred locations"
        return "Yes", f"{hits[0].title()} is {where}"
    saved = prefs.get("willing_to_relocate")
    if saved:
        return saved, ""
    if places:
        return None, f"This place isn't in your preferred locations ({', '.join(p.title() for p in places)}): answer yourself"
    return None, ""


def total_experience(profile: dict):
    """Years of work experience from the Experience entries ("YYYY-MM" start/end)."""
    jobs = profile.get("experience") or []
    if not jobs:
        return "0", ""
    months = 0
    today = date.today()
    for job in jobs:
        start = re.fullmatch(r"(\d{4})-(\d{2})", job.get("start") or "")
        end = re.fullmatch(r"(\d{4})-(\d{2})", job.get("end") or "")
        if not start:
            return None, ""
        ey, em = (int(end.group(1)), int(end.group(2))) if end else (today.year, today.month)
        months += max(0, (ey - int(start.group(1))) * 12 + em - int(start.group(2)))
    years = months // 12
    return str(years), f"From your experience entries: about {years} year(s) {months % 12} month(s)"


def education_summary(profile: dict):
    edu = profile.get("education") or {}
    lines = []
    d = edu.get("degree") or {}
    if d.get("name"):
        field = " ".join(x for x in (d.get("branch"), f"({d['specialization']})" if d.get("specialization") else "") if x)
        score = f", CGPA {d['cgpa']}/{d.get('cgpa_scale') or 10}" if d.get("cgpa") else ""
        year = f" ({d['graduation_year']})" if d.get("graduation_year") else ""
        lines.append(f"{d['name']} {field}, {d.get('college', '')}{year}{score}".replace(" ,", ","))
    for key, name in (("class_12", "Class 12"), ("class_10", "Class 10")):
        c = edu.get(key) or {}
        if c.get("school") or c.get("percentage"):
            pct = f": {c['percentage']}%" if c.get("percentage") else ""
            lines.append(f"{name}, {c.get('school', '')} {c.get('board', '')} ({c.get('year', '')}){pct}".replace(" ()", ""))
    certs = [c.get("name") for c in profile.get("certifications") or [] if c.get("name")]
    if certs:
        lines.append("Certifications: " + "; ".join(certs))
    return ("\n".join(lines) or None), "Built from your education and certifications: check it fits"


# ---------- choosing options ----------

INSTITUTE_KEYS = {"education.degree.college", "education.degree.university"}
STOPWORDS = {"of", "and", "the", "for", "in", "at", "university", "college", "institute"}


def institute_names(key: str, profile: dict) -> list[str]:
    """Every name the student's college goes by: the field's own value first, then the rest."""
    degree = get_path(profile, "education.degree") or {}
    own = degree.get(key.split(".")[-1])
    names = [own, degree.get("college"), degree.get("university"), *(degree.get("college_aliases") or [])]
    return list(dict.fromkeys(n.strip() for n in names if n and n.strip()))


def initials(name: str) -> str:
    """'Vellore Institute of Technology, Amaravati' -> 'vit' (the part before the comma)."""
    head = words(name.split(",")[0]).split()
    return "".join(w[0] for w in head if w not in {"of", "and", "the", "for", "in", "at"})


def choose_institute(key: str, d: dict, profile: dict):
    """College dropdowns list the same place many ways: "VIT-AP", "Vellore Institute
    of Technology", "Vellore Institute of Technology, Amaravati". Try every name
    the student saved; only an exact hit is green, anything else is a yellow guess,
    and if several campuses fit equally we ask instead of guessing."""
    options = [o for o in d.get("options") or [] if not PLACEHOLDER.match(words(o))]
    names = institute_names(key, profile)
    if not names:
        return None, "missing", f"No {describe_key(key)} in your profile"

    for name in names:
        m = match_option(name, options)
        if m and m.exact:
            return m.option, "filled", ""

    vocab = set(" ".join(words(n) for n in names).split()) - STOPWORDS
    tokens = set(" ".join(words(n) for n in names).split())
    candidates = [o for o in options
                  if any(match_option(n, [o]) for n in names) or (len(initials(o)) >= 2 and initials(o) in tokens)]
    if not candidates:
        return None, "missing", f'No option matches your college ("{names[0]}"). Add the name used here to "Other names for your college".'

    score = {o: len(set(words(o).split()) & vocab) for o in candidates}
    best = max(score.values())
    top = [o for o in candidates if score[o] == best]
    if len(top) > 1:
        return None, "review", f"Several options could be your college ({', '.join(top[:4])}). Choose yours."
    return top[0], "review", "Closest match for your college: check the name and campus"

def choose_option(key: str, value, d: dict, profile: dict):
    """For dropdowns/radios: returns (option_text or None, status, reason)."""
    options = d.get("options") or []
    text = ", ".join(value) if isinstance(value, list) else str(value)

    # A count asked as Yes/No ("Standing backlogs? Yes / No"): 0 -> No, more -> Yes.
    yes_no = {words(o): o for o in options if words(o) in ("yes", "no")}
    if len(yes_no) == 2 and re.fullmatch(r"\d+(\.\d+)?", text.strip()):
        answer = "no" if float(text) == 0 else "yes"
        return yes_no[answer], "filled", ""

    if key in INSTITUTE_KEYS:
        return choose_institute(key, d, profile)
    if key == "personal.phone_country_code":
        return choose_country_code(text, d)

    # Branch + specialization: prefer "CSE (AI and ML)" over plain "CSE".
    if key == "education.degree.branch":
        spec = get_path(profile, "education.degree.specialization")
        if spec:
            both = [o for o in options if mentions(o, text) and mentions(o, spec)]
            if both:
                return both[0], "filled", ""

    m = match_option(text, options)
    if not m:
        # Only for years/numbers (e.g. graduation 2027 not listed). Never for personal
        # details: "Other" for a Gender question would be wrong data.
        other = next((o for o in options if words(o) in ("other", "others", "other please specify")), None)
        if other and re.fullmatch(r"\d{4}|\d+(\.\d+)?", text.strip()):
            return other, "review", f'"{shorten(text)}" isn\'t listed, so "{other}" was picked'
        return None, "missing", f'No option matches "{shorten(text)}"'
    if m.exact:
        return m.option, "filled", ""
    return m.option, "review", f'Closest option picked for "{shorten(text)}"'


def tick_options(values, d: dict):
    """For checkbox lists: returns (list of option texts to tick, status, reason)."""
    values = values if isinstance(values, list) else [values]
    ticked = [o for o in d.get("options") or [] if any(match_option(v, [o]) for v in values)]
    if not ticked:
        return None, "missing", "None of these options are in your profile"
    return ticked, "review", f"Ticked: {', '.join(ticked)}. Check nothing is missing."


# ---------- the agent ----------

def map_field(d: dict, key: str | None, profile: dict) -> dict:
    action = {"field_id": d["id"], "key": key, "value": None, "source": "rules"}

    if key is None or key == "file_other":
        return {**action, "status": "skipped", "reason": "Not something in your profile"}
    if key == "resume_file":
        return {**action, "status": "review", "reason": "Resume upload box: the extension attaches your saved resume"}
    if key == "consent":
        return {**action, "status": "review", "reason": "Declaration/consent: read it and tick it yourself"}
    if key == YES_NO:
        answer = answer_yes_no(f"{d.get('label', '')} {d.get('helper_text', '')}", profile)
        if answer.value is None:
            return {**action, "status": answer.status, "reason": answer.reason, "source": "evidence"}
        # A text box, or a custom dropdown whose options appear only when opened: "Yes" / "No"
        # (the extension picks the matching option when it opens the dropdown).
        if not d.get("options") and d.get("kind") in ("text", "textarea", "combobox", "", None):
            return {**action, "value": answer.value, "status": answer.status, "reason": answer.reason, "source": "evidence"}
        m = match_option(answer.value, d.get("options") or [])
        if not m:
            return {**action, "status": "missing", "reason": f'No "{answer.value}" option ({answer.reason})', "source": "evidence"}
        return {**action, "value": m.option, "status": answer.status, "reason": answer.reason, "source": "evidence"}
    if key == "education.masters":
        return {**action, "status": "skipped", "reason": "Master's/PG field: you have no Master's in your profile, so it's left empty"}
    if key == "skills.all" and is_tag_box(d):
        # Tag box: the extension adds each skill by typing it and clicking the matching suggestion
        # (never pressing Enter). Up to "max N" if the form says so.
        top = top_skills(profile)
        limit = re.search(r"\b(?:up to|upto|max(?:imum)?|top|at most|choose)\s*(\d+)\b", hint_text(d))
        if limit:
            top = top[: int(limit.group(1))]
        if not top:
            return {**action, "status": "missing", "reason": "No skills in your profile"}
        return {**action, "value": top, "mode": "tags", "status": "review",
                "reason": "Added one at a time from the site's suggestions: check the tags"}
    if key == FREE_TEXT:
        # Placeholder; Assemble replaces it with a verified draft if there is one.
        return {**action, "status": "review", "reason": "Open question: write your answer"}

    value, review = resolve_value(key, profile, d)
    if value is None and review:
        return {**action, "status": "review", "reason": review}
    if value is None:
        hint = " (only CGPA is saved; conversion formulas differ by university)" if key.endswith("percentage_equivalent") else ""
        return {**action, "status": "missing", "reason": f"No {describe_key(key)} in your profile{hint}"}

    kind = d.get("kind", "text")
    options = d.get("options") or []

    if kind == "checkbox" and len(options) > 1:
        ticked, status, reason = tick_options(value, d)
        return {**action, "value": ticked, "status": status, "reason": reason}

    if key == "personal.phone_country_code" and kind in CHOICE_KINDS:
        option, status, reason = choose_country_code(value, d)
        return {**action, "value": option, "status": status, "reason": reason}

    if kind in CHOICE_KINDS and options:
        option, status, reason = choose_option(key, value, d, profile)
        if status == "filled" and review:
            status, reason = "review", review
        return {**action, "value": option, "status": status, "reason": reason}

    if kind == "combobox":
        # A site dropdown whose options appear only when opened: the extension opens it and picks
        # the value (or the first of a list of alternatives). If it can't, it says "Pick X" itself.
        return {**action, "value": value, "status": "review" if review else "filled", "reason": review}
    text = ", ".join(value) if isinstance(value, list) else value
    if isinstance(text, str) and kind != "textarea" and "\n" in text:
        # A one-line box drops line breaks, so list answers would run together ("...(IBM)AWS Academy...").
        text = "; ".join(line.strip(" •-") for line in text.splitlines() if line.strip())
    return {**action, "value": text, "status": "review" if review else "filled", "reason": review}


def mapper(state: dict) -> dict:
    by_id = {f["id"]: f for f in state["fields"]}
    # If the form has its own country-code field, phone boxes get the number without the code.
    has_code_field = any(c["key"] == "personal.phone_country_code" for c in state["classified"])
    plan = []
    # Context from earlier questions: "Coding Platform: LeetCode" makes the
    # "Profile / Evidence Link" box a few questions later the LeetCode link.
    platform, platform_at = None, -10
    language, language_at = None, -10
    for i, c in enumerate(state["classified"]):
        d = by_id[c["field_id"]]
        key = c["key"]
        if has_code_field and key in ("personal.phone", "personal.alternate_phone"):
            d = {**d, "_national_phone": True}
        if i - platform_at <= 3 and key in (None, "links.portfolio", "links.coding_profile") \
                and re.search(r"\b(profile|evidence)\b.*\b(link|url)\b|\bprofile url\b", (d.get("label") or "").lower()):
            key = "links.coding_profile"
        if key == "links.coding_profile":
            d = {**d, "_platform": platform}
        # "Language: English" then "Proficiency": the level for that language.
        if i - language_at <= 2 and key is None \
                and re.fullmatch(r"(language )?(proficiency|fluency)( level)?|level", norm(d.get("label"))):
            key = "languages.proficiency"
        if key == "languages.proficiency":
            d = {**d, "_language": language}
        action = map_field(d, key, state.get("profile") or {})
        if key == "links.coding_platform" and action.get("value"):
            value = action["value"]
            platform, platform_at = (value[0] if isinstance(value, list) else value), i
        if key == "languages_spoken" and isinstance(action.get("value"), str) and "," not in action["value"]:
            language, language_at = action["value"], i
        plan.append(action)
    # "What are your strengths?" with no saved answer: let the Drafter write one (local LLM only).
    from services import ollama_client
    free_text = list(state.get("free_text_fields") or [])
    if ollama_client.use_llm(state):
        free_text += [a["field_id"] for a in plan
                      if (a.get("key") or "").startswith("standard_answers") and a.get("value") is None
                      and by_id[a["field_id"]].get("kind") in ("text", "textarea") and a["field_id"] not in free_text]
    return {"fill_plan": plan, "free_text_fields": free_text, "trace": ["mapper"]}


def marking_scheme(p: dict, d: dict):
    """"Marking Scheme" in a marks table: "Percentage" for 10th / 12th / diploma (the profile keeps
    percentages there), "CGPA" for the degree when the profile has a CGPA. Returns (value, review)."""
    label = f"{d.get('label', '')} {d.get('section', '')}".lower()
    school = re.search(r"\b(10th|12th|x|xii|ssc|hsc|tenth|twelfth|diploma|school|class)\b", label)
    degree = (p.get("education") or {}).get("degree") or {}
    wanted = "Percentage" if school or not degree.get("cgpa") else "CGPA"
    options = [o for o in d.get("options") or [] if o.strip() and not PLACEHOLDER.search(o)]
    if not options:
        return wanted, ""   # a custom dropdown: the extension picks the matching option when it opens
    pattern = (r"percent|%|marks" if wanted == "Percentage"
               else r"c?gpa|\bcpi\b|\bspi\b|grade point|\bgrades?\b|pointer|10[- ]?point|out of 10|/ ?10\b")
    pick = next((o for o in options if re.search(pattern, o, re.I)), None)
    return (pick, "") if pick else (None, f"Pick your marking scheme ({wanted})")


def result_status(p: dict, d: dict):
    """"Result Status": 10th / 12th / diploma are declared; the degree is "awaited / pursuing" until
    its graduation month has passed. Returns (value, review)."""
    label = f"{d.get('label', '')} {d.get('section', '')}".lower()
    school = re.search(r"\b(10th|12th|ssc|hsc|tenth|twelfth|diploma|school|class)\b", label)
    degree = (p.get("education") or {}).get("degree") or {}
    done = True
    if not school:
        year = str(degree.get("graduation_year") or "").strip()
        if not year.isdigit():
            return None, "Pick your result status"
        month = int(degree.get("graduation_month") or 6)
        done = (int(year), month) < (date.today().year, date.today().month)
    options = [o for o in d.get("options") or [] if o.strip() and not PLACEHOLDER.search(o)]
    if not options:
        return ("Declared" if done else "Pursuing"), ""
    pattern = (r"declared|passed|completed|complete|pass\b|result out" if done
               else r"awaited|pursuing|appearing|in progress|ongoing|not declared|final year|expected|studying")
    pick = next((o for o in options if re.search(pattern, o, re.I)), None)
    return (pick, "") if pick else (None, "Pick your result status (" + ("declared" if done else "still studying") + ")")
