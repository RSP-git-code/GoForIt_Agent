"""Pulls the useful facts out of a placement / job email.

Input: {"id", "from", "subject", "date" (YYYY-MM-DD), "body"} (plain text).
Output: company, role, deadline, apply links, and the eligibility rules the
email states (CGPA cut-off, branches, batch, 10th/12th %, backlogs).

Rules only (no ML yet; the local LLM can help in a later phase). Links are
only collected, never opened (CLAUDE.md rule 8).
"""

import re
from datetime import date, datetime

# ---------- is this a job / placement email? ----------

JOB_WORDS = re.compile(
    r"\b(hiring|recruitment|recruiting|placement|campus drive|off[- ]campus|on[- ]campus|drive|internship|intern|"
    r"job opening|opening|vacancy|vacancies|apply|application|register|registration|opportunity|shortlist\w*|"
    r"assessment|online test|ctc|stipend|eligib\w*)\b", re.I)
NOT_JOB = re.compile(r"\b(newsletter|webinar recording|order (shipped|confirmed)|otp|password reset|invoice|receipt)\b", re.I)


def is_job_email(subject: str, body: str) -> bool:
    text = f"{subject} {body[:3000]}"
    if NOT_JOB.search(subject):
        return False
    return len(set(m.lower() for m in JOB_WORDS.findall(text))) >= 2


# ---------- company and role ----------

FIELD_LINE = r"^\s*(?:\*|-|•)?\s*(?:{names})\s*[:\-–]\s*(.+?)\s*$"
COMPANY_NAMES = r"company(?: name)?|name of (?:the )?(?:company|organi[sz]ation)|organi[sz]ation|employer|recruiter"
ROLE_NAMES = r"role|position|job title|job role|designation|profile|post|opening"
GENERIC_SENDERS = re.compile(r"placement|career|training|tpo|cdc|t&p|noreply|no-reply|notification|team|office|cell|hr\b", re.I)


def _field(body: str, names: str) -> str | None:
    m = re.search(FIELD_LINE.format(names=names), body, re.I | re.M)
    return m.group(1).strip(" .*") if m else None


def extract_company(subject: str, body: str, sender: str) -> str | None:
    found = _field(body, COMPANY_NAMES)
    if found:
        return found[:80]
    name = r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3}?)"
    keywords = r"(?i:campus drive|campus|off[- ]campus|on[- ]campus|hiring|recruitment|internship|placement|drive|opportunity)"
    candidates = [
        # Body: "Gamma Labs is hiring...", "Acme Analytics is visiting campus..."
        re.search(rf"(?m)^\s*{name}\s+(?i:is|are)\s+(?i:hiring|visiting|recruiting|looking|conducting|inviting)", body[:800]),
        # Subject: "Placement Drive: Acme", "Off-campus opportunity: Gamma Labs ML ..."
        re.search(rf"{keywords}\s*(?i:by|for|at|with|from|[:\-–|])\s*{name}(?=\s+(?:[A-Z]{{2,}}|[A-Z][a-z]+ (?:Intern|Engineer|Analyst|Developer|Scientist))|\s*[|\-–(]|$)", subject),
        # Subject: "BigBank Hiring - ...", "Acme | Campus Drive 2027"
        re.search(rf"^{name}\s*(?:\||[-–:])?\s*{keywords}", subject),
    ]
    for m in candidates:
        if m:
            found = m.group(1).strip(" -–:|")
            if found and not GENERIC_SENDERS.search(found) and not re.fullmatch(r"(?i)(off|on|dear|hi|hello|the|we|our)", found):
                return found
    # Sender display name, unless it's a placement cell / generic mailbox.
    name = re.sub(r"\s*<.*?>", "", sender or "").strip(' "')
    if name and not GENERIC_SENDERS.search(name) and "@" not in name:
        return name
    return None


def extract_role(subject: str, body: str) -> str | None:
    found = _field(body, ROLE_NAMES)
    if found:
        return found[:80]
    m = re.search(r"\b(?:for (?:the )?(?:role|position) of|hiring for|hiring|for)\s+((?:[A-Z][\w/&+.\-]*\s*){1,6}?)(?:\s+(?:role|position|at|-|–|\||\(|20\d\d)|$)", subject)
    return m.group(1).strip() if m else None


# ---------- deadline ----------

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
DEADLINE_CUE = re.compile(
    r"(last date(?: (?:to|for) (?:apply|register|registration|submission|applying))?|deadline|apply (?:by|before)|"
    r"register (?:by|before)|registration (?:closes|deadline|ends)|closes on|on or before|due (?:date|by)|before)"
    r"\s*(?:is|:|-|–|on)?\s*", re.I)
DATE_PATTERNS = [
    # 10/10/2026, 10-10-2026, 10.10.2026 (Indian day-first)
    (re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b"), "dmy"),
    # 10 Oct 2026, 10th October, 2026, 10-Oct-26
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-]+([A-Za-z]{3,9})[,\s\-]+(\d{2,4})\b"), "dMy"),
    # October 10, 2026 / Oct 10th 2026
    (re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), "Mdy"),
    # 10th October (no year)
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Za-z]{3,9})\b"), "dM"),
]


def _year(y: str) -> int:
    y = int(y)
    return y + 2000 if y < 100 else y


def _month(name: str) -> int | None:
    return MONTHS.get(name[:3].lower())


def parse_date(text: str, ref: date) -> date | None:
    """First date in `text`. A date without a year is the next one on/after `ref`."""
    for pattern, kind in DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            if kind == "dmy":
                d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
            elif kind == "dMy":
                d, mo, y = int(m.group(1)), _month(m.group(2)), _year(m.group(3))
            elif kind == "Mdy":
                mo, d, y = _month(m.group(1)), int(m.group(2)), int(m.group(3))
            else:
                d, mo = int(m.group(1)), _month(m.group(2))
                y = ref.year if mo and (mo, d) >= (ref.month, ref.day) else ref.year + 1
            if not mo:
                continue
            return date(y, mo, d)
        except ValueError:
            continue
    return None


def extract_deadline(body: str, subject: str, ref: date) -> date | None:
    for text in (subject, body):
        for cue in DEADLINE_CUE.finditer(text):
            found = parse_date(text[cue.end(): cue.end() + 60], ref)
            if found:
                return found
    return None


# ---------- links (collected, never opened) ----------

URL = re.compile(r"https?://[^\s<>\"')\]]+")
SKIP_LINK = re.compile(r"unsubscribe|mailto:|facebook\.com|twitter\.com|x\.com/|instagram\.com|youtube\.com|"
                       r"\.(png|jpg|jpeg|gif)(\?|$)|/track|/pixel|utm_medium=email_footer|privacy|terms", re.I)
FORM_HOSTS = re.compile(r"forms\.gle|docs\.google\.com/forms|myworkdayjobs|tally\.so|greenhouse\.io|lever\.co|"
                        r"keka\.com|oraclecloud\.com|successfactors|taleo|careers|apply|jobs\.|superset|unstop|hackerearth|hirist", re.I)
LINKEDIN_LIKE = re.compile(r"linkedin\.com|naukri\.com|indeed\.", re.I)


def extract_links(body: str) -> list[str]:
    links = []
    for url in URL.findall(body):
        url = url.rstrip(".,;")
        if SKIP_LINK.search(url) or url in links:
            continue
        links.append(url)
    # Application forms first; job-board links last (they're only listed, never automated).
    return sorted(links, key=lambda u: (0 if FORM_HOSTS.search(u) and not LINKEDIN_LIKE.search(u) else 2 if LINKEDIN_LIKE.search(u) else 1))


# ---------- eligibility rules stated in the email ----------

BRANCHES = {
    "CSE": r"\bcse\b|computer science|\bcs\b",
    "IT": r"\bit\b(?! is)|information technology",
    "ECE": r"\bece\b|electronics and communication",
    "EEE": r"\beee\b|electrical and electronics",
    "AI/ML": r"\bai ?(?:&|and|/)? ?ml\b|artificial intelligence",
    "Data Science": r"data science",
    "Mechanical": r"\bmech\b|mechanical",
    "Civil": r"\bcivil\b",
}


def extract_eligibility(body: str) -> dict:
    t = body.lower()
    rules = {}
    m = re.search(r"(?:cgpa|cpi|gpa|pointer)[^\d\n]{0,30}?(\d{1,2}(?:\.\d{1,2})?)", t)
    if m and float(m.group(1)) <= 10:
        rules["min_cgpa"] = float(m.group(1))
    for level, pattern in (("min_10th", r"(?:10th|tenth|ssc|class x\b|x th)"), ("min_12th", r"(?:12th|twelfth|hsc|intermediate|class xii)")):
        m = re.search(pattern + r"[^\n%]{0,40}?(\d{2}(?:\.\d+)?)\s*%", t)
        if m:
            rules[level] = float(m.group(1))
    if re.search(r"\b(all|any) (branches|streams|disciplines)\b|\bopen to all\b", t):
        rules["branches"] = ["All"]
    else:
        branch_text = " ".join(re.findall(r"(?:branch(?:es)?|stream|discipline|eligible (?:branches|degrees?))[^\n]{0,150}", t))
        found = [name for name, pattern in BRANCHES.items() if re.search(pattern, branch_text)]
        if found:
            rules["branches"] = found
    # Every year in a sentence that talks about batches: "2026 and 2027 batch".
    years = sorted({int(y) for s in re.findall(r"[^.\n]*(?:batch|pass(?:ing)?[- ]?out|graduat)[^.\n]*", t)
                    for y in re.findall(r"\b(20\d\d)\b", s)})
    if years:
        rules["batches"] = years
    if re.search(r"no (?:active |current |standing )?backlogs?|zero backlogs?|without (?:any )?backlogs?", t):
        rules["no_active_backlogs"] = True
    return rules


def _branch_matches(profile_branch: str, wanted: list[str]) -> bool:
    b = (profile_branch or "").lower()
    return any(re.search(BRANCHES[w], b) for w in wanted if w in BRANCHES)


def check_eligibility(rules: dict, profile: dict) -> tuple[bool | None, list[str]]:
    """(True / False / None if nothing to check, reasons). Compares only stated rules."""
    edu = (profile or {}).get("education") or {}
    degree = edu.get("degree") or {}
    problems, checked = [], 0

    def number(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    if "min_cgpa" in rules and number(degree.get("cgpa")) is not None:
        checked += 1
        if number(degree["cgpa"]) < rules["min_cgpa"]:
            problems.append(f"needs CGPA ≥ {rules['min_cgpa']} (you have {degree['cgpa']})")
    for key, level, name in (("min_10th", "class_10", "10th"), ("min_12th", "class_12", "12th")):
        have = number((edu.get(level) or {}).get("percentage"))
        if key in rules and have is not None:
            checked += 1
            if have < rules[key]:
                problems.append(f"needs {name} ≥ {rules[key]:g}% (you have {have:g}%)")
    if rules.get("branches") == ["All"]:
        checked += 1  # open to all branches: a rule you meet
    elif rules.get("branches") and degree.get("branch"):
        checked += 1
        spec = f"{degree.get('branch', '')} {degree.get('specialization', '')}"
        if not _branch_matches(spec, rules["branches"]):
            problems.append(f"branches: {', '.join(rules['branches'])}")
    if rules.get("batches") and degree.get("graduation_year"):
        checked += 1
        if number(degree["graduation_year"]) not in [float(y) for y in rules["batches"]]:
            problems.append(f"batch {', '.join(map(str, rules['batches']))} (you graduate in {degree['graduation_year']})")
    if rules.get("no_active_backlogs"):
        checked += 1
        if number(degree.get("active_backlogs")) not in (None, 0.0):
            problems.append("no active backlogs allowed")

    if not checked:
        return None, []
    return (not problems), problems


# ---------- one call for the Inbox agent ----------

def extract(email: dict) -> dict:
    subject, body = email.get("subject", ""), email.get("body", "")
    try:
        ref = datetime.strptime(email.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        ref = date.today()
    return {
        "email_id": email.get("id"),
        "received": ref.isoformat(),
        "is_job": is_job_email(subject, body),
        "company": extract_company(subject, body, email.get("from", "")),
        "role": extract_role(subject, body),
        "deadline": (d.isoformat() if (d := extract_deadline(body, subject, ref)) else None),
        "links": extract_links(body),
        "eligibility": extract_eligibility(body),
    }
