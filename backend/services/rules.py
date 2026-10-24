"""Rule-based field classifier (Page Analyzer's first pass).

Ported from the Phase 2 extension rules. Given a field descriptor, returns:
  - a profile path like "education.class_12.percentage"
  - a virtual key the Mapper understands ("skills.all", "consent", ...)
  - "free_text_question" (an open question for the Drafter)
  - None (unrelated field, e.g. "How did you hear about us?")

This is also the "rules baseline" the trained classifier must beat in Phase 6.
"""

import re

FREE_TEXT = "free_text_question"
SKIP = "skip"  # a rule meaning "this is NOT a profile field" (e.g. Phone Extension)
YES_NO = "yes_no_question"

# Yes/No questions whose answer is stored in the profile as-is.
DIRECT_YES_NO = {"preferences.willing_to_relocate", "preferences.work_authorization_india", "preferences.requires_sponsorship",
                 "education.degree.active_backlogs", "education.degree.backlog_history", "education.gap_years",
                 "relatives.at_company"}


def is_yes_no(options: list[str]) -> bool:
    """True if the real (non-placeholder) options are just Yes and No."""
    from services.option_match import strip_marker
    real = {norm(strip_marker(o)) for o in options} - {"", "select", "select an option", "choose", "please select", "select one"}
    return len(real) >= 2 and real <= {"yes", "no", "y", "n"}


def norm(s: str | None) -> str:
    """Lowercase, split camelCase/snake_case, keep % and ? so "10th %" still works."""
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")
    s = s.lower().replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9%?]+", " ", s).strip()


LEVELS = {
    "class_10": re.compile(r"\b(10th|10 th|tenth|ssc|sslc|matric|matriculation|class (10|x)|std (10|x)|x th|x std|x standard|grade (10|x))\b|^x\b"),
    "class_12": re.compile(r"\b(12th|12 th|twelfth|hsc|intermediate|inter|puc|pre university|class (12|xii)|std (12|xii)|xii|senior secondary|higher secondary|grade (12|xii))\b"),
    "diploma": re.compile(r"\bdiploma\b"),
    "degree": re.compile(r"\b(b ?tech|b e|be degree|bachelor|bachelors|ug|undergrad|undergraduate|graduation|graduating|degree|engineering|college|university|cgpa|gpa|cpi|semester|sem|final)\b"),
}

# Mentions a name/phone/email but is about someone else. Plurals matter:
# norm() drops apostrophes, so "Father's" becomes "fathers".
SOMEONE_ELSE = re.compile(r"\b(fathers?|mothers?|parents?|guardians?|spouses?|reference|referee|referrer|referred|referral|emergency|recruiters?|managers?|hr)\b")


# Countries other than India named in work-authorization / visa questions (text is norm()ed: "U.S." -> "u s").
FOREIGN_COUNTRY = re.compile(r"\b(united states|usa|u s(?: a)?|in the us|in us|america|canada|united kingdom|uk|singapore|"
                             r"portugal|germany|ireland|netherlands|sweden|australia|japan|france|poland|dubai|uae|"
                             r"h ?1 ?b|opt|green card|eu|europe)\b")


def _r(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def education_key(t: str) -> str | None:
    level = next((name for name in ("class_10", "class_12", "diploma", "degree") if LEVELS[name].search(t)), None)
    if not level:
        return None
    base = f"education.{level}"
    scoreish = re.search(r"\b(percentage|marks|cgpa|gpa|score)\b|%", t)

    if re.search(r"\bboard\b", t):
        return None if level == "degree" else f"{base}.board"
    # "Aggregated till date", "as on date": not a date question.
    t = re.sub(r"\b(till|to|as on|up to|upto) date\b", " ", t)
    cg = re.search(r"\b(cgpa|gpa|cpi|sgpa|pointer|grade point)\b", t)
    pc = re.search(r"%|\bpercent|\bpercentage|\bmarks\b|\baggregate\b", t)
    if cg or pc:
        if level != "degree":
            return f"{base}.percentage"
        if cg and (not pc or cg.start() < pc.start()):
            return f"{base}.cgpa"
        return f"{base}.percentage_equivalent"
    # Start and end dates (Workday and Oracle ask "From" and "To" as month + year).
    # Degree: start_* / graduation_*. Class 10, 12, diploma: start_* / year, month (of passing).
    started = re.search(r"\b(start|started|from|join|joining|admission|admitted|commencement|enrol)", t)
    degree = level == "degree"
    if re.search(r"\bmonth\b", t):
        if degree:
            return f"{base}.start_month" if started else f"{base}.graduation_month"
        return f"{base}.start_month" if started else f"{base}.month"
    if re.search(r"\bdate\b", t):
        if degree:
            return f"{base}.start_date" if started else f"{base}.graduation_date"
        return f"{base}.start_date" if started else f"{base}.passing_date"
    if re.search(r"\b(year|yop|passing|passed|pass out|batch)\b", t):
        if degree:
            return f"{base}.start_year" if started else f"{base}.graduation_year"
        return f"{base}.start_year" if started else f"{base}.year"
    if re.search(r"\b(school|college|institute|institution)\b", t) and not scoreish:
        if level == "degree":
            return f"{base}.university" if re.search(r"\buniversity\b", t) and not re.search(r"\bcollege\b", t) else f"{base}.college"
        if level == "diploma":
            return f"{base}.institute"
        return f"{base}.school"
    if re.search(r"\buniversity\b", t) and level == "degree" and not re.search(r"\b(percentage|marks|cgpa|gpa)\b|%", t):
        return f"{base}.university"
    if re.search(r"\b(stream|branch|department|discipline|specialization|specialisation|major)\b", t):
        if level == "class_12":
            return f"{base}.stream"
        if level == "class_10":
            return None
        if level == "degree" and re.search(r"\bspeciali[sz]ation\b", t):
            return f"{base}.specialization"
        return f"{base}.branch"
    if re.search(r"\b(cgpa|gpa|cpi|sgpa|pointer|grade point)\b", t):
        return f"{base}.cgpa" if level == "degree" else f"{base}.percentage"
    if re.search(r"%|\bpercent|\bpercentage|\bmarks|\baggregate|\bscore|\bgrade\b|\bresult", t):
        return f"{base}.percentage_equivalent" if level == "degree" else f"{base}.percentage"
    if level == "degree" and re.search(r"\b(degree|course|program|programme|qualification)\b", t):
        return f"{base}.name"
    return None


# Checked before the education rules, so "College email ID" is an email and
# "University roll no" is a registration number.
EARLY_RULES = [
    (_r(r"\b(first name|given name|fname|forename)\b"), "personal.first_name"),
    (_r(r"\bmiddle name\b"), "personal.middle_name"),
    (_r(r"\b(last name|surname|family name|lname)\b"), "personal.last_name"),
    # Master's / PG fields (a bachelor's student leaves these empty; the Mapper decides).
    (_r(r"\b(masters?|m tech|mtech|m e|pg|post ?grad\w*|post graduation|mba|mca|m sc|msc)\b.*\b(degree|percentage|cgpa|gpa|year|passing|branch|specialization|college|university|institute|course|marks)\b"
        r"|\b(degree|percentage|year|branch|college) (of|in) (masters?|pg|post ?graduation)\b"), "education.masters"),
    (_r(r"\b(institute|institution|college|university|official|student|academic)\b.*\be ?mail\b|\be ?mail\b.*\b(institute|college|university|official)\b"), "personal.college_email"),
    (_r(r"\be ?mail\b"), "personal.email"),
    # A link someone wants (certificate, video, resume on Drive), not the thing itself.
    (_r(r"\bresume\b.*\b(link|drive|onedrive|url|share)\b|\b(share|upload)\b.*\bresume\b"), "links.resume_link"),
    (_r(r"\b(link|url)\b.*\bcertificat|\bcertificat\w*\b.*\b(link|url|drive)\b"), SKIP),
    (_r(r"\b(jee main|jee mains)\b"), "education.entrance_exams.jee_main"),
    (_r(r"\b(jee adv|jee advanced)\b"), "education.entrance_exams.jee_advanced"),
    (_r(r"\b(math|maths|mathematics|physics|chemistry|biology|english|science)\b.*\b(gpa|percentage|marks|score|%)"), "subject_marks"),
    (_r(r"\b(highest|educational) (educational )?qualification\b.*\b(progress|completed|pursuing|status)\b|\bin progress\b.*\bcompleted\b"), "education.degree.status"),
    (_r(r"\b(highest|educational) (educational )?qualification\b|^qualification\b"), "education.degree.name"),
    (_r(r"\b(name of )?(your )?(current|last|present|latest)( or |/| )?(last )?(institution|institute|college|university)\b|\b(institution|institute|college) name\b"), "education.degree.college"),
    (_r(r"\b(prior|previous|past)?\s*(internship|work) (/ ?work )?experience\b"), "experience.summary"),
    # "Coding Platform: LeetCode / Codeforces / CodeChef..." and its profile link.
    (_r(r"\bcoding (profile|platform)s? (link|url)\b|\b(competitive programming|coding) profile\b"), "links.coding_profile"),
    (_r(r"\b(coding|competitive programming) platforms?\b"), "links.coding_platform"),
    # Papers and memberships are FACTS: only from their own profile lists, never an AI draft and never
    # borrowed from achievements or certifications (an AI draft once called IBM / AWS certificates
    # "professional bodies").
    (_r(r"\bpublications?\b|\bpapers? (published|presented|presentations?)\b|\bresearch papers?\b|\bpaper presentations?\b|"
        r"\b(journal|conference) papers?\b"), "publications"),
    (_r(r"\bprofessional (bodies|body|societ(y|ies)|associations?|memberships?)\b|\bmemberships?\b|\baffiliations?\b|"
        r"\bmember of (any|a|an)\b|\bassociations? (with|and)\b"), "memberships"),
    (_r(r"\bextra[- ]?curricular|\bcoding (competitions?|contests?)\b|\bhackathons?\b"), "achievements"),
    (_r(r"\b(country code|country calling code|dial(ling)? code|isd( code)?|calling code|phone code)\b"), "personal.phone_country_code"),
    (_r(r"\b(alternate|alternative|secondary|other) (phone|mobile|contact|number|no)\b"), "personal.alternate_phone"),
    # camelCase split turns "WhatsApp" into "whats app"
    # Phone sub-fields that are NOT the number itself.
    (_r(r"\b(device type|number type|phone type|type of (phone|number|device))\b"), "personal.phone_type"),
    (_r(r"\b(extension|ext)\b"), SKIP),
    (_r(r"captcha|\b(enter|type) the (characters|code|text) (shown|in the image|above)\b"), SKIP),
    # One-time codes the site sends you ("Enter OTP", name="mobileOtp"): never profile data,
    # and "mobile" in the name must not make it a phone field.
    (_r(r"\botp\b|\bone time (password|code|pin)\b|\bverification code\b|\bpass ?code\b"), SKIP),
    (_r(r"\b(phone|mobile|mob|cell|telephone|whats ?app|contact no|contact number)\b"), "personal.phone"),
    (_r(r"\b(dob|date of birth|birth date|birthdate|birthday|d o b)\b"), "personal.date_of_birth"),
    (_r(r"\blinked ?in\b"), "links.linkedin"),
    (_r(r"\bgit ?hub\b"), "links.github"),
    (_r(r"\bleet ?code\b"), "links.leetcode"),
    # A SCHOOL roll / seat number ("10th · Roll Number" in a marks table) is not the college
    # registration number. It isn't in the profile, so it gets flagged instead of guessed.
    (_r(r"\b(10th|class (10|x)|ssc|tenth|matric\w*)\b.*\b(roll|seat|hall ticket)\b"), "education.class_10.roll_number"),
    (_r(r"\b(12th|class (12|xii)|hsc|twelfth|intermediate|inter|puc)\b.*\b(roll|seat|hall ticket)\b"), "education.class_12.roll_number"),
    (_r(r"\b(diploma|school|board)\b.*\b(roll|seat|hall ticket)\b"), "education.school_roll_number"),
    # "Marking Scheme": Percentage for school, CGPA for the degree (the mapper picks).
    (_r(r"\b(marking|grading|grade|evaluation) (scheme|system|type|pattern)\b"), "education.marking_scheme"),
    # "Result Status": Declared / Awaited / Pursuing (not the marks themselves).
    (_r(r"\b(result|course|degree|qualification) status\b|\bresults? (declared|awaited)\b|\bpursuing or completed\b"), "education.result_status"),
    (_r(r"\b(registration|reg|roll|enrollment|enrolment|register|admission|student id)\b.*\b(no|number|num|id)\b|\b(usn|prn)\b"), "education.degree.registration_number"),
    (_r(r"\b(active|current|live|standing|pending)\b.*\b(backlogs?|arrears?|kt)\b"), "education.degree.active_backlogs"),
    (_r(r"\b(backlogs?|arrears?|kt)\b.*\b(history|total|ever|past|cleared)\b|\b(history|total|any|past)\b.*\b(backlogs?|arrears?)\b"), "education.degree.backlog_history"),
    (_r(r"\b(backlogs?|arrears?|kt)\b"), "education.degree.active_backlogs"),
    (_r(r"\bgap\b.*\b(reason|why|explain|describe)\b|\b(reason|explain)\b.*\bgap\b"), "education.gap_reason"),
    (_r(r"\bgap\b"), "education.gap_years"),
    # "Experience (in years)", "Total experience", "Years of experience", "How many years of experience"
    (_r(r"\b(total|overall|relevant|work|professional)? ?experience\b.*\b(years?|yrs|months?)\b"
        r"|\b(years?|yrs) of (work |relevant |professional |industry )?experience\b|\bhow many years\b"), "experience.total_years"),
]

LATE_RULES = [
    (_r(r"\b(gender|sex)\b"), "personal.gender"),
    (_r(r"\b(caste|reservation category|social category)\b|^category\b"), "personal.category"),
    (_r(r"\b(nationality|citizenship)\b"), "personal.nationality"),
    # "Country/Territory", "Country of residence": where you live (not where the job is).
    (_r(r"^(current |home )?(country|country territory|country region|country of residence|residence country)$"),
     "personal.country"),
    (_r(r"\b(pin ?code|postal code|zip ?code|zip)\b|^pin\b"), "personal.pincode"),
    (_r(r"\baddress\b"), "personal.permanent_address"),
    # Workday's education "Year" boxes say which year only in their code name:
    # education-832--firstYearAttended-dateSectionYear (from) / --lastYearAttended-... (to).
    # (Before the "education ..." summary rule, which would otherwise claim them.)
    (_r(r"\bfirst year attended\b|\byear of joining\b|\bjoining year\b|\bstart(ing)? year\b"), "education.degree.start_year"),
    (_r(r"\blast year attended\b|\bend(ing)? year\b|\bcompletion year\b"), "education.degree.graduation_year"),
    (_r(r"^(education|qualifications?|educational (background|qualifications?)|education (or|and) (relevant )?training|courses|relevant training)\b"), "education.summary"),
    (_r(r"\b(portfolio|personal website|personal site|website|blog)\b"), "links.portfolio"),
    # Education fields asked without saying which level: assume the degree.
    (_r(r"\b(year of passing|passing year|pass out year|passout year|graduation year|year of graduation|batch)\b"), "education.degree.graduation_year"),
    (_r(r"\bspeciali[sz]ation\b"), "education.degree.specialization"),
    (_r(r"\b(branch|discipline|major|department|field of study|area of study|fields? of studies)\b"), "education.degree.branch"),
    # Preferences (before city/location so "preferred location" doesn't become city)
    (_r(r"\brelocat|\bopen (to|for) (any|all) locations?\b|\bany location\b|\banywhere in india\b|\blocations? across india\b"), "preferences.willing_to_relocate"),
    (_r(r"\b(preferred|preference)\b.*\b(location|city|cities)\b|\blocation preference\b"), "preferences.preferred_locations"),
    (_r(r"\bnotice period\b"), "preferences.notice_period"),
    # "When can you start?", "Earliest joining date", "How soon are you available to start?"
    (_r(r"\b(available|availability) to (start|join)|\bwhen (can|could|would) you (start|join)|\bwhen are you available\b"
        r"|\bhow soon\b|\bearliest (possible )?(start|joining|join)( date)?\b|\b(date of joining|joining date)\b"
        r"|\bable to start\b"), "preferences.available_from"),
    (_r(r"\b(expected|desired)\b.*\b(ctc|salary|compensation|stipend|pay)\b"), "preferences.expected_ctc"),
    (_r(r"\bsponsor"), "preferences.requires_sponsorship"),
    (_r(r"\b(authori[sz]ed to work|work authori[sz]ation|legally (eligible|authori[sz]ed)|eligible to work)\b"), "preferences.work_authorization_india"),
    (_r(r"\b(permanent|native)\b.*\b(city|town|district)\b|\bhome ?town\b|\bnative place\b"), "personal.permanent_city"),
    (_r(r"\b(permanent|native|home)\b.*\bstate\b"), "personal.permanent_state"),
    (_r(r"\b(city|location|town)\b"), "personal.current_city"),
    (_r(r"^(current |home |native )?state\b|\b(current|present|resident|residential)\b.*\bstate\b|\bstate\s*$|\bstate of residence\b"), "personal.current_state"),
    (_r(r"\b(current|present|latest|most recent)( or (previous|last|most recent))? (company|employer|organi[sz]ation)\b"), "experience.current_company"),
    (_r(r"\b(current|present|latest|most recent)( or previous)? (job )?(title|designation|position)\b"), "experience.current_title"),
    (_r(r"\bprogramming languages?\b"), "skills.languages"),
    (_r(r"\blanguages? (known|spoken|you (speak|know))\b|\bspoken languages?\b"), "languages_spoken"),
    (_r(r"\b(skills?|skill ?sets?|technologies|tech stack|tools)\b|\bused in a project\b"), "skills.all"),
    (_r(r"\bcertificat"), "certifications.all"),
    (_r(r"\b(achievements?|awards?|accomplishments?)\b"), "achievements"),
    (_r(r"\bprojects?\b"), "projects.all"),
    # All the ways forms ask for your summary.
    (_r(r"\b(tell us about yourself|tell us more about you|about yourself|introduce yourself|describe yourself)\b"
        r"|^(about me|about you|summary|bio|profile|highlights?|key highlights?|objective)$"
        r"|\b(profile|professional|career|personal|candidate|brief|short) (summary|highlights?|profile|overview|objective)\b"
        r"|\bsummary\s*(and |/|&)?\s*highlights?\b|\bhighlights?\s*(and |/|&)?\s*summary\b"
        r"|\bsummary (of|about) (your ?self|you|your profile)\b|\bcareer objective\b"), "standard_answers.about_me"),
    (_r(r"\bwhy should we hire\b|\bwhy (are you|would you be) (a )?(good|great|right|best) fit\b"), "standard_answers.why_hire_me"),
    (_r(r"\bstrengths?\b"), "standard_answers.strengths"),
    (_r(r"\bweakness"), "standard_answers.weaknesses"),
    # Name last, so "college name", "school name", "company name" are caught earlier
    (_r(r"\b(full name|your name|candidate name|student name|applicant name|name of (the )?(student|candidate|applicant)|(enter|type) (your )?(full )?name)\b|^name\b"), "personal.full_name"),
]

CONSENT = _r(r"\b(i agree|agree|consent|declare|declaration|certify|acknowledge|terms|privacy|accurate|true to the best)\b")
QUESTION = _r(r"\?|^(why|how|what|describe|explain|tell|share|briefly|write)\b|\bcover letter\b|\badditional information\b")
CHOICE_KINDS = {"select", "radio", "checkbox", "combobox"}


def _first_match(rules, t: str) -> str | None:
    return next((key for pattern, key in rules if pattern.search(t)), None)


# "Are you / Do you / Have you ... ?" or "(Y/N)": a question answered with Yes or No.
# (Matched on norm()ed labels: lowercase, punctuation gone, so "(Y/N)" reads "y n".)
CLOSED_QUESTION = _r(r"^(if not .*? )?(are|do|did|have|has|is|was|were|will|would|can|could) you\b|\by n\b|\byes no\b")
ASKS_DETAILS = _r(r"\b(describe|explain|elaborate|details?|specify|mention|list|name|which|why|how|please share|if yes)\b")
# "If not an Indian citizen, do you hold an OCI card?": your nationality answers it,
# so it's not a "depends on another answer" follow-up you must handle yourself.
CONDITIONAL = _r(r"^if (others?|yes|no|so|any|applicable|not|other)\b")
ANSWERABLE_CONDITION = _r(r"^if not (an? )?(indian )?citizen|^if not (an? )?citizen of india|^if not of indian")


# Questions about health, disability or accommodations: never filled or AI-drafted (the
# student decides whether to share anything). Matched on norm()ed text.
SENSITIVE = _r(r"\b(accessibility|accommodations?|accommodate|disabilit\w*|disabled|impairment|medical|"
               r"health condition|special (assistance|needs)|neurodiverg\w*|reasonable adjustments?)\b")


# Diversity / EEO choice questions -> profile["diversity"] (optional; empty = left for you). norm()ed text.
DIVERSITY = [
    (_r(r"\b(diversity|inclusion|equal (employment )?opportunit\w*|eeo)\b.*\b(consent|agree|declaration|acknowledge)\b"
        r"|\bconsent\b.*\b(diversity|inclusion)\b"), "diversity.consent"),
    (_r(r"\b(ethnic\w*|race|racial)\b"), "diversity.ethnicity"),
    (_r(r"\bveteran\b"), "diversity.veteran"),
    (_r(r"\b(disabilit\w*|disabled|neurodiver\w*)\b"), "diversity.disability"),
]

# Relatives / family at the company (answered from profile["relatives"]). Matched on norm()ed text.
RELATIVES = _r(r"\b(relatives?|family members?|relations?|related to|close friends?)\b.*\b(work\w*|employ\w*|serving|associated)\b"
               r"|\b(work\w*|employ\w*)\b.*\b(relatives?|family members?)\b")
RELATIVE_DETAILS = _r(r"\b(provide|share|mention|give|specify|list|details?|name|names|information)\b")

# Matched on norm()ed labels ("ai/ml" reads "ai ml").
SKILL_EXPERIENCE = _r(r"^((hands on|practical|prior|relevant|your) )?experience (in|with|of|using|on) \S|"
                      r"^how much (hands on |practical )?experience (do )?you (have|hold) (in|with|of|on) \S")


def _conditional(label: str) -> bool:
    return bool(CONDITIONAL.match(label or "")) and not ANSWERABLE_CONDITION.match(label or "")


def guard(d: dict, key: str | None) -> str | None:
    """Safety checks applied to the classifier's answer too (the rules apply them inside classify):
    "If yes/others..." follow-ups are yours, files are files, foreign-country visa questions are
    yours, Yes/No dropdowns go to the evidence engine, saved long answers never go in a dropdown."""
    if key in (None, "none", SKIP):
        return None
    label = norm(d.get("label"))
    t = label or norm(" ".join(d.get(k) or "" for k in ("aria_label", "placeholder", "name", "element_id")))
    kind = d.get("kind", "text")
    if _conditional(label) or SENSITIVE.search(t):
        return None
    if kind == "file":  # an upload box: the resume only if it says resume/CV
        return "resume_file" if re.search(r"\b(resume|cv)\b", t) else "file_other"
    if key in ("resume_file", "file_other"):
        return None
    if key in ("preferences.work_authorization_india", "preferences.requires_sponsorship") \
            and FOREIGN_COUNTRY.search(t) and not re.search(r"\bindia\b", t):
        return YES_NO if kind in CHOICE_KINDS and is_yes_no(d.get("options") or []) else None
    if kind in CHOICE_KINDS and is_yes_no(d.get("options") or []) and key not in DIRECT_YES_NO \
            and key not in (YES_NO, "consent"):
        return YES_NO
    if key.startswith("standard_answers") and kind in CHOICE_KINDS:
        return None
    return key


def classify(d: dict) -> str | None:
    """d is a field descriptor dict (see app/schemas.py FieldDescriptor)."""
    label = norm(d.get("label"))
    extra = norm(" ".join(d.get(k) or "" for k in ("aria_label", "placeholder", "name", "element_id")))
    t = label or extra
    if not t:
        return None

    kind = d.get("kind", "text")
    if _conditional(label):
        return None  # only applies after another answer; you decide
    # Diversity / equal-opportunity dropdowns: answered only from your optional "Diversity answers".
    if kind in CHOICE_KINDS:
        for pattern, key in DIVERSITY:
            if pattern.search(t):
                return key
    if SENSITIVE.search(t):
        return None  # accessibility / health / disability: only you decide what to share
    # "Do you have any relatives working within HSBC group?" and its "please provide name..." follow-up.
    if RELATIVES.search(t):
        return "relatives.details" if RELATIVE_DETAILS.search(t) else "relatives.at_company"
    # "Hands on experience in Python?", "How much experience you hold in AI/ML?" in a text box:
    # answered from your projects and skills ("Years of experience" stays a number elsewhere).
    if kind in ("text", "textarea") and SKILL_EXPERIENCE.search(label or "") and not re.search(r"\byears?\b", label or ""):
        return "skills.experience"
    section = norm(d.get("section"))
    if re.fullmatch(r"(spoken |preferred )?languages?( known| spoken)?", label or "") and kind != "textarea":
        return "languages_spoken"
    if re.fullmatch(r"(language )?(proficiency|fluency)( level)?|level", label or "") and re.search(r"\blanguage", section):
        return "languages.proficiency"

    if kind == "file":
        return "resume_file" if re.search(r"\b(resume|cv)\b", f"{t} {extra}") else "file_other"
    if kind == "checkbox" and len(d.get("options") or []) <= 1 and CONSENT.search(t):
        return "consent"
    if SOMEONE_ELSE.search(t):
        return None

    looks_like_question = bool(QUESTION.search(t)) and len(t.split()) >= 4
    # "From" / "To" boxes inside an education entry (Workday, Oracle). The label
    # alone says nothing, so the hidden name/id or helper text must say "education".
    section = norm(d.get("section"))
    # A bare "URL" / "Link" box: the section heading says which link it wants.
    if re.fullmatch(r"(url|link|links|website|web address|website url|profile url|link url|address)", label or ""):
        if label != "address" or re.search(r"\b(website|web|url|link)", section):
            for pattern, key in ((r"git ?hub", "links.github"), (r"linked ?in", "links.linkedin"),
                                 (r"leet ?code", "links.leetcode")):
                if re.search(pattern, section):
                    return key
            if label != "address" or section:
                return "links.portfolio"

    if re.fullmatch(r"(from|to|start|end|start date|end date|from date|to date)( actual or expected)?( date| year)?", label or "") \
            and re.search(r"\b(education|school|university|college|degree|attended|academic)\b", f"{extra} {norm(d.get('helper_text'))} {section}"):
        return "education.entry.from" if re.match(r"(from|start)", label) else "education.entry.to"

    # A bare "School" / "Institution" box: the section heading says which level.
    # In an Oracle/Workday "Education" entry it's your college (highest education).
    if re.fullmatch(r"(school|school name|institution|institution name|name of (the )?(school|institution))", label or ""):
        level = next((name for name in ("class_10", "class_12", "diploma") if LEVELS[name].search(section)), None)
        if level:
            return f"education.{level}." + ("institute" if level == "diploma" else "school")
        if re.search(r"\b(education|academic|qualification|degree)", section) or not section:
            return "education.degree.college" if section else None

    # "Start of Course", "End of Course", "Course completion date": the degree's dates.
    course = re.fullmatch(r"(?:(start|starting|commencement|beginning|joining|end|ending|completion|finish)(?: date| year| month)? of (?:the |your )?"
                          r"(?:course|program|programme|degree|study|studies)|(?:course|program|programme|degree) "
                          r"(start|end|completion|commencement|joining)(?: date| year| month)?)", label or "")
    if course:
        prefix = "start" if (course.group(1) or course.group(2)) in ("start", "starting", "commencement", "beginning", "joining") else "graduation"
        unit = re.search(r"\b(year|month)\b", label)
        return f"education.degree.{prefix}_{unit.group(1) if unit else 'date'}"

    key = _first_match(EARLY_RULES, t) or education_key(t) or _first_match(LATE_RULES, t)
    if key == SKIP:
        return None
    # The education summary is for big text boxes whose VISIBLE label asks for it,
    # never for a box matched only through its hidden name/id.
    if key == "education.summary" and (kind != "textarea" or not label):
        return None

    # A long-answer box that mentions e.g. "Python" is an open question, not
    # the skills list. Saved standard answers are the exception.
    # A dropdown labelled "Mobile Phone" next to the number box is the country code.
    if key in ("personal.phone", "personal.alternate_phone") and kind in CHOICE_KINDS:
        return "personal.phone_country_code"

    # The saved answers ("authorized: Yes", "need sponsorship: No") are true for India
    # only. For a job in another country they would be false, so you answer those.
    if key in ("preferences.work_authorization_india", "preferences.requires_sponsorship") \
            and FOREIGN_COUNTRY.search(t) and not re.search(r"\bindia\b", t):
        return YES_NO if kind in CHOICE_KINDS and is_yes_no(d.get("options") or []) else None

    long_question = looks_like_question and kind == "textarea"
    # Yes/No questions ("Do you have a Bachelor's degree?", "Are you fluent in
    # English?") are answered from evidence (services/evidence.py), not mapped
    # to a field, unless the profile stores the answer directly.
    if kind in CHOICE_KINDS and is_yes_no(d.get("options") or []) and key not in DIRECT_YES_NO:
        return None if key == "consent" or CONSENT.search(t) else YES_NO
    # The same kind of question in a plain text box ("Are you an Indian Citizen?",
    # "Do you hold an OCI card? (Y/N)"): answered "Yes"/"No" from evidence. Not when
    # the box asks for details, and not when a profile field answers it directly.
    # Also custom dropdowns whose Yes/No options only appear when opened (SuccessFactors, Workday).
    if kind in ("text", "", "combobox") and not d.get("options") and CLOSED_QUESTION.search(label or "") \
            and not ASKS_DETAILS.search(t) and (key is None or key == FREE_TEXT or key == "personal.nationality"):
        return YES_NO

    # Saved long answers never go into a choice field: "Tell us more about yourself
    # and we'll keep you updated? Yes / No" is an opt-in, not the About-me answer.
    if key and key.startswith("standard_answers") and kind in CHOICE_KINDS:
        return None
    LONG_OK = ("standard_answers", "achievements", "experience.summary", "skills.all", "publications", "memberships")
    if key and (not long_question or key.startswith(LONG_OK)):
        return key

    # If the label didn't help, try name/id/placeholder (e.g. name="urls[GitHub]"). Only for short,
    # vague labels: when the label is a real question, it wins. (A Globant form asked "Additional
    # information about accessibility?" with the copied placeholder "Tell us a little bit about yourself".)
    if not key and label and extra and not looks_like_question and len(label.split()) <= 3:
        from_extra = classify({**d, "label": ""})
        if from_extra and from_extra != FREE_TEXT:
            return from_extra

    if kind not in CHOICE_KINDS and (kind == "textarea" or looks_like_question):
        return FREE_TEXT
    return None
