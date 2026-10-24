"""Answers Yes/No eligibility questions from evidence in the profile.

"Do you have a Bachelor's degree?", "Are you fluent in English?", "Do you have
experience with Excel?" are not profile fields. Instead of a rule per wording,
we (1) work out the TOPIC (degree level, language, tool/skill, work experience),
(2) pull out the SUBJECT ("English", "Excel"), (3) look for evidence in the
profile, and (4) answer only from that evidence, saying where it was found.

Never guesses "No" from missing data: if nothing is found, the question is
flagged for the student. (The one deliberate "No" is for work-experience
questions when the profile lists no experience, and it is always flagged
for review with that reason.)

Returns Answer(value, status, reason): value is "Yes", "No" or None.
"""

import re
from dataclasses import dataclass
from datetime import date

from services.option_match import words


@dataclass
class Answer:
    value: str | None
    status: str  # filled | review | missing
    reason: str


# ---------- topic: degree level ----------

LEVELS = [  # rank, pattern
    (1, r"\b(10th|tenth|ssc|class 10|class x|matric\w*|secondary school)\b"),
    (2, r"\b(12th|twelfth|hsc|class 12|class xii|intermediate|higher secondary|senior secondary|high school diploma)\b"),
    (2.5, r"\bdiploma\b"),
    (3, r"\b(bachelor\w*|b tech|btech|b e|b sc|bsc|undergraduate|ug degree|engineering degree|graduate degree|university degree|college degree)\b"),
    (4, r"\b(master\w*|m tech|mtech|m s|msc|m sc|mba|postgraduate|pg degree)\b"),
    (5, r"\b(phd|ph d|doctorate|doctoral)\b"),
]
LEVEL_NAMES = {1: "Class 10", 2: "Class 12", 2.5: "a diploma", 3: "a bachelor's degree", 4: "a master's degree", 5: "a PhD"}


def _level_of(text: str) -> float | None:
    t = words(text)
    for rank, pattern in reversed(LEVELS):  # most specific (highest) first
        if re.search(pattern, t):
            return rank
    return None


def _completed(year: str, month: str | None, today: date) -> bool | None:
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    m = int(month) if month and str(month).isdigit() else 6  # unknown month: assume mid-year
    return (y, m) <= (today.year, today.month)


def answer_degree(question: str, profile: dict, today: date) -> Answer | None:
    asked = _level_of(question)
    if asked is None:
        return None
    edu = profile.get("education") or {}
    degree = edu.get("degree") or {}
    have = []  # (rank, name, completed?)
    if (edu.get("class_10") or {}).get("year"):
        have.append((1, "Class 10", _completed(edu["class_10"]["year"], edu["class_10"].get("month"), today)))
    if (edu.get("class_12") or {}).get("year"):
        have.append((2, "Class 12", _completed(edu["class_12"]["year"], edu["class_12"].get("month"), today)))
    if degree.get("name"):
        rank = _level_of(degree["name"]) or 3
        have.append((rank, degree["name"], _completed(degree.get("graduation_year"), degree.get("graduation_month"), today)))
    if not have:
        return Answer(None, "missing", "No education saved in your profile")

    highest = max(have, key=lambda h: h[0])
    exact = [h for h in have if h[0] == asked]
    if exact:
        _, name, done = exact[0]
        if done:
            return Answer("Yes", "filled", f"You have {name}")
        if done is False:
            return Answer(None, "review",
                          f"You're still pursuing {name}: answer Yes only if they accept a degree in progress")
        return Answer(None, "review", f"Check: {name} has no completion year saved")
    if highest[0] > asked:
        return Answer("Yes", "review", f"Your profile has {highest[1]}, a higher level than {LEVEL_NAMES[asked]}")
    return Answer("No", "review", f"Your highest education in the profile is {highest[1]}, not {LEVEL_NAMES[asked]}")


# ---------- topic: languages ----------

KNOWN_LANGUAGES = ["english", "hindi", "marathi", "telugu", "tamil", "kannada", "malayalam", "bengali", "gujarati",
                   "punjabi", "urdu", "odia", "german", "french", "spanish", "japanese", "mandarin", "chinese", "korean"]
LANGUAGE_CUE = r"\b(speak|spoken|write|written|read|fluent\w*|proficien\w*|communicat\w*|language|native|bilingual)\b"


def answer_language(question: str, profile: dict) -> Answer | None:
    t = words(question)
    asked = [lang for lang in KNOWN_LANGUAGES if re.search(rf"\b{lang}\b", t)]
    if not asked or not re.search(LANGUAGE_CUE, t):
        return None
    # "English (Fluent)" counts as English: drop a saved level in brackets or after ":" / "-".
    spoken = {words(re.split(r"\s*[(:\-]", str(s))[0]) for s in profile.get("languages_spoken") or []}
    missing = [lang for lang in asked if lang not in spoken]
    if not missing:
        return Answer("Yes", "filled", f"{', '.join(a.title() for a in asked)} is in your languages")
    return Answer(None, "review", f"{', '.join(m.title() for m in missing)} isn't in your languages: answer yourself")


# ---------- topic: citizenship ----------

def answer_citizenship(question: str, profile: dict) -> Answer | None:
    """"Are you an Indian citizen?", "Do you hold an OCI card?", "Citizenship of any other
    country?" from personal.nationality. India doesn't allow dual citizenship, so an
    Indian citizen holds no other citizenship and doesn't need an OCI card."""
    t = words(question)
    if not re.search(r"\bcitizen\w*|\bnationality\b|\boci\b|\boverseas citizen", t):
        return None
    nationality = words((profile.get("personal") or {}).get("nationality") or "")
    if not nationality:
        return Answer(None, "review", "Add your nationality in your profile")
    indian = nationality in ("indian", "india")
    if re.search(r"\boci\b|\boverseas citizen", t):
        return Answer("No", "filled", "You're an Indian citizen, so an OCI card doesn't apply") if indian else \
            Answer(None, "review", "OCI card: answer yourself")
    if re.search(r"\b(other than india|any other country|another country|dual|other citizenship)\b", t):
        return Answer("No", "review", "Your nationality is Indian (India doesn't allow dual citizenship): check") if indian else None
    if re.search(r"\bindia\b|\bindian\b", t):
        return Answer("Yes" if indian else "No", "filled", f"Your nationality: {nationality.title()}")
    return None


# ---------- topic: work experience ----------

def answer_work_experience(question: str, profile: dict) -> Answer | None:
    t = words(question)
    if not re.search(r"\b(professional|work|industry|full time|job|employment|internship|intern)\b.*\bexperience\b"
                     r"|\bexperience\b.*\b(professional|work|industry|full time|internship)\b"
                     r"|\b(worked|employed) (as|at|in)\b|\bhave you (done|completed) an internship\b", t):
        return None
    jobs = profile.get("experience") or []
    wants_internship = re.search(r"\bintern(ship)?s?\b", t) and not re.search(r"\bnon intern", t)
    if wants_internship:
        hits = [j for j in jobs if re.search(r"\bintern", f"{j.get('role', '')} {j.get('summary', '')}", re.I)]
    else:
        hits = [j for j in jobs if not re.search(r"\bintern", j.get("role", ""), re.I)]
    if hits:
        return Answer("Yes", "review", f"Your profile lists: {hits[0].get('role')} at {hits[0].get('company')}")
    kind = "internships" if wants_internship else "non-internship work experience"
    return Answer("No", "review", f"Your profile lists no {kind}: check this is right")


# ---------- topic: current employment, previous employers, offers ----------

def _current_jobs(profile: dict) -> list[dict]:
    return [j for j in profile.get("experience") or []
            if j.get("company") and (not j.get("end") or re.search(r"present|current|now", j["end"], re.I))]


def answer_employment(question: str, profile: dict) -> Answer | None:
    t = words(question)
    jobs = profile.get("experience") or []

    # "Are you already placed / holding an offer?" -> the profile's own answer.
    if re.search(r"\b(already placed|been placed|placed already|hold\w* (a |an |any )?(job )?offers?|accepted (a |an |any )?offer|offer letter|have (a |an |any )?(job )?offers?)\b", t):
        saved = ((profile.get("preferences") or {}).get("has_job_offer") or "").strip()
        if saved:
            return Answer(saved, "filled", "From 'Already placed / holding a job offer?' in your profile")
        return Answer(None, "review", "Set 'Already placed / holding a job offer?' in your profile")

    # "Are you currently employed / working / partnered / associated with any company?"
    if re.search(r"\b(currently|presently|at present|right now)\b.*\b(employed|working|associated|partnered|engaged|affiliated|attached|serving|bond|contract)\b"
                 r"|\bare you (employed|working)\b|\b(associated|partnered|affiliated|tied up|engaged) with any (company|organi[sz]ation|employer|firm)\b", t):
        current = _current_jobs(profile)
        if current:
            return Answer("Yes", "review", f"Your profile lists a current role at {current[0]['company']}")
        return Answer("No", "filled", "Your profile has no current job")

    # "Have you ever worked for Acme before?" / "Are you an Ex Employee of Acme?"
    m = re.search(r"\b(?:worked|been employed|employed|interned|been an employee)\b.*?\b(?:for|at|with|by|of)\s+(.+?)$", t) \
        or re.search(r"\b(?:ex|former|previous|past) ?(?:employee|employees|intern|staff|alumn\w*)\s+(?:of|at|with|from)\s+(.+?)$", t)
    # "Have you been employed ... by X" asks about the past too, even without "ever".
    if m and re.search(r"\b(ever|previously|before|earlier|past|prior|former|ex)\b|\bex ?employee|\bhave you been (employed|working)", t):
        company = re.sub(r"\b(before|previously|earlier|in the past|ever|any of its \w+|or its \w+)\b", " ", m.group(1)).strip()
        if company in ("any company", "a company", "any organisation", "any organization"):
            if jobs:
                return Answer("Yes", "review", f"Your profile lists work at {jobs[0].get('company')}")
            return Answer("No", "filled", "Your profile has no work experience")
        hits = [j for j in jobs if j.get("company") and (words(j["company"]) in company or company in words(j["company"]))]
        if hits:
            return Answer("Yes", "review", f"Your profile lists {hits[0]['company']}")
        name = company.title() if len(company) <= 40 else "That employer"  # long = the rest of the sentence, not a name
        return Answer("No", "filled" if not jobs else "review", f"{name} isn't in your work experience")
    return None


# ---------- topic: tools / skills / knowledge ----------

TOOL_ALIASES = {
    "microsoft office": ["ms office", "microsoft office", "office 365", "microsoft 365"],
    "excel": ["excel", "ms excel", "microsoft excel", "spreadsheets"],
    "powerpoint": ["powerpoint", "ms powerpoint"],
    "machine learning": ["machine learning", "ml", "scikit learn", "tensorflow", "pytorch", "keras"],
    "deep learning": ["deep learning", "neural networks", "tensorflow", "keras", "pytorch", "lstm", "rnn", "cnn"],
    "sql": ["sql", "mysql", "postgresql", "sqlite"],
    "cloud": ["aws", "azure", "gcp", "cloud"],
    "llm": ["llm", "llms", "large language model", "langchain", "rag", "gemini", "generative ai"],
}
SKILL_CUE = (r"\b(experience|experienced|familiar|familiarity|knowledge|knowledgeable|proficien\w*|skilled|expertise|"
             r"worked|used|hands on|comfortable|know how|understanding)\b")


def _profile_corpus(profile: dict) -> list[tuple[str, str]]:
    """(where, text) pairs to search, most direct evidence first. No contact details."""
    out = []
    for group, items in (profile.get("skills") or {}).items():
        for s in items:
            out.append(("your skills", s))
    for p in profile.get("projects") or []:
        out.append((f"project '{p.get('title', '')}'", " ".join(p.get("tech") or [])))
        out.append((f"project '{p.get('title', '')}'", f"{p.get('title', '')} {p.get('summary', '')}"))
    for e in profile.get("experience") or []:
        out.append((f"experience at {e.get('company', '')}", f"{e.get('role', '')} {e.get('summary', '')}"))
    for c in profile.get("certifications") or []:
        out.append(("your certifications", c.get("name", "")))
    return out


def _subject(question: str) -> str | None:
    t = words(question)
    # Greedy ".*" makes this the LAST cue: "hands-on knowledge of LangChain" -> "LangChain".
    m = re.search(rf".*{SKILL_CUE}\s+(?:with|in|on|of|using|at)?\s*(.+)$", t)
    if not m:
        return None
    # Drop generic category words: "SQL databases" -> "SQL", "cloud platforms" -> "cloud".
    subject = re.sub(r"\b(products?|applications?|apps?|tools?|software|technolog(y|ies)|frameworks?|librar(y|ies)|"
                     r"platforms?|databases?|systems?|services?|concepts?|techniques?|such as|like|etc|and its|the|any|"
                     r"a|an|some|basic|advanced|strong|good)\b", " ", m.group(2))
    return re.sub(r"\s+", " ", subject).strip() or None


def answer_skill(question: str, profile: dict) -> Answer | None:
    subject = _subject(question)
    if not subject:
        return None
    terms = [s.strip() for s in re.split(r"\band\b|\bor\b|,|/", subject) if s.strip()]
    corpus = [(where, f" {words(text)} ") for where, text in _profile_corpus(profile)]
    for term in terms:
        aliases = TOOL_ALIASES.get(term, [term])
        for where, text in corpus:
            for alias in aliases:
                if f" {words(alias)} " in text:
                    status = "filled" if where == "your skills" and alias == term else "review"
                    return Answer("Yes", status, f"Found '{alias}' in {where}")
    return Answer(None, "review",
                  f"Couldn't find {' / '.join(terms)} in your profile: answer yourself (and add it to your skills if you have it)")


# ---------- entry point ----------

def answer_yes_no(question: str, profile: dict, today: date | None = None) -> Answer:
    today = today or date.today()
    for topic in (lambda q, p: answer_degree(q, p, today), answer_citizenship, answer_language, answer_employment,
                  answer_work_experience, answer_skill):
        result = topic(question, profile)
        if result:
            return result
    return Answer(None, "review", "Yes/No question not covered by your profile: answer yourself")
