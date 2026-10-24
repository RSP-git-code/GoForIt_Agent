"""Benchmark: which local model should the Form Reader use?

    backend/.venv/Scripts/python ml/llm/form_reader_bench.py qwen3:1.7b llama3.2:3b qwen3:4b

Questions are the ones the rules got wrong on real forms this week (Oct 2026),
laid out as three form pages so context matters, with a MADE-UP student profile
(nothing personal in git). Some questions must be left empty ("trap": the
profile doesn't say), to measure invented answers.

Scores per model: correct answers, invented answers (answered a trap, or an
answer the grounding check rejects), and seconds per page on this laptop.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from agents.form_reader import ground, profile_facts, read_form  # noqa: E402
from services.option_match import words  # noqa: E402

PROFILE = {
    "personal": {"full_name": "Asha Verma", "first_name": "Asha", "last_name": "Verma", "email": "asha@example.com",
                 "phone": "+91 9876543210", "date_of_birth": "2004-01-15", "gender": "Female", "nationality": "Indian",
                 "current_city": "Pune", "current_state": "Maharashtra"},
    "links": {"linkedin": "https://linkedin.com/in/asha", "github": "https://github.com/asha",
              "leetcode": "https://leetcode.com/u/asha/", "other": ["CodeChef:https://www.codechef.com/users/asha"]},
    "education": {
        "degree": {"name": "B.Tech", "branch": "Computer Science and Engineering", "specialization": "AI and ML",
                   "branch_full": "Computer Science with Specialization in Artificial Intelligence and Machine Learning",
                   "college": "Example Institute of Technology, Pune", "start_year": "2023", "start_month": "07",
                   "graduation_year": "2027", "graduation_month": "05", "cgpa": "8.42", "cgpa_scale": "10",
                   "percentage_equivalent": "84.2", "active_backlogs": 0},
        "class_12": {"board": "CBSE", "percentage": "93.4", "math_percentage": "96"},
        "class_10": {"board": "CBSE", "percentage": "90.6"},
    },
    "skills": {"languages": ["Python", "Java", "C++"], "ml_ai": ["scikit-learn", "PyTorch", "LangChain"], "web": ["Django"]},
    "projects": [{"title": "Resume Matcher", "summary": "RAG-based resume and job matching app.", "tech": ["Python", "LangChain"]}],
    "experience": [],
    "achievements": ["Co-lead, Data Science Club (2024-2025)", "Smart India Hackathon 2024 finalist"],
    "languages_spoken": ["English", "Hindi", "Marathi", "Japanese"],
    "preferences": {"notice_period": "0", "available_from": "2026-11-23", "willing_to_relocate": "Yes",
                    "preferred_locations": ["Pune", "Bangalore", "Hyderabad"], "expected_ctc": "6,00,000",
                    "has_job_offer": "No", "work_authorization_india": "Yes", "requires_sponsorship": "No"},
}


def q(i, label, kind="text", options=(), section="", placeholder=""):
    return {"id": f"q{i}", "label": label, "kind": kind, "options": list(options), "section": section,
            "placeholder": placeholder, "helper_text": ""}


PLATFORMS = ["LeetCode", "Codeforces", "CodeChef", "HackerRank", "GeeksforGeeks", "Other", "Not Registered"]
# (field, accepted answers) - None means "must be left empty".
PAGES = [
    [  # like the Deloitte form
        (q(1, "Graduation percentage - (Convert your CGPA into a percentage, numbers only)"), ["84.2"]),
        (q(2, "12th percentage / Diploma - (numbers only)"), ["93.4"]),
        (q(3, "Coding Platform", "radio", PLATFORMS), ["LeetCode", "CodeChef"]),
        (q(4, "Coding Rating / Rank - Example (1850)"), None),
        (q(5, "Profile / Evidence Link - (Profile URL)"), ["https://leetcode.com/u/asha/", "https://www.codechef.com/users/asha"]),
        (q(6, "Hackathon / Competition Details - Example (Smart India Hackathon)"), ["Smart India Hackathon 2024 finalist", "Smart India Hackathon 2024"]),
        (q(7, "Hackathon / Competition Achievement - Example (Finalist)"), ["Finalist"]),
        (q(8, "Additional Foreign Language known - Example (French)"), ["Japanese"]),
        (q(9, "Are you an Ex Employee of Deloitte?", "select", ["Yes", "No"]), ["No"]),
        (q(10, "Are you an Indian Citizen?", "select", ["Yes", "No"]), ["Yes"]),
        (q(11, "If not an Indian citizen, do you hold an OCI Card? (Y/N)"), ["No", "N", "NA", "Not applicable"]),
        (q(12, "How did you hear about this opportunity?"), None),
    ],
    [  # education + preferences
        (q(13, "Branch ( branch and specialization)"), ["Computer Science with Specialization in Artificial Intelligence and Machine Learning"]),
        (q(14, "What is your current CGPA (out of 10)?"), ["8.42"]),
        (q(15, "Grade-XII Math GPA/Percentage (mention NA, if not applicable)"), ["96"]),
        (q(16, "Name of Current/Last Institution"), ["Example Institute of Technology, Pune", "Example Institute of Technology"]),
        (q(17, "Are you willing to relocate to Bengaluru?", "radio", ["Yes", "No"]), ["Yes"]),
        (q(18, "Expected CTC (per annum)"), ["6,00,000", "600000", "6 LPA", "6,00,000 per annum"]),
        (q(19, "Programming languages you have expertise in", "checkbox", ["Java", "Python", "React", "Go", "AI/ML"]), ["Python, Java", "Java, Python"]),
        (q(20, "Years of Experience", "select", ["0-1", "1-2", "2-3", "3+"]), ["0-1"]),
    ],
    [  # eligibility questions with traps
        (q(21, "Are you legally authorized to work in the United States?", "select", ["Yes", "No"]), None),
        (q(22, "Do you hold an Indian Passport?", "select", ["Yes", "No"]), None),
        (q(23, "Do you have any active backlogs?", "select", ["Yes", "No"]), ["No"]),
        (q(24, "Do you currently hold a job offer?", "select", ["Yes", "No"]), ["No"]),
        (q(25, "Your T-shirt size"), None),
    ],
]


def same(a: str, b: str) -> bool:
    return words(a) == words(b) or words(a).replace(" ", "") == words(b).replace(" ", "")


def rules_answers(fields: list[dict]) -> dict[str, tuple]:
    """What the current pipeline (rules + Mapper + evidence engine) gives: {id: (answer or None, key)}."""
    from agents.mapper import mapper
    from services.rules import classify
    classified = [{"field_id": f["id"], "key": classify(f)} for f in fields]
    plan = mapper({"fields": fields, "classified": classified, "profile": PROFILE})["fill_plan"]
    out = {}
    for a in plan:
        value = a.get("value")
        if isinstance(value, list):
            value = ", ".join(value)
        out[a["field_id"]] = (value if value not in ("", None) else None, a.get("key"))
    return out


def score(answer, expected) -> tuple[bool, bool]:
    """(correct, invented) for one answer."""
    given = answer not in (None, "", "null")
    if expected is None:
        return not given, given
    return given and any(same(str(answer), e) for e in expected), False


def run(model: str) -> dict:
    facts = profile_facts(PROFILE)
    correct = invented = rejected = blank = 0
    rules_ok = rules_bad = hybrid_ok = hybrid_bad = 0
    seconds, rows = [], []
    for page in PAGES:
        fields = [f for f, _ in page]
        # Hybrid: the LLM only sees the questions the rules left unanswered (and never Yes/No eligibility ones).
        by_rules = rules_answers(fields)
        answers, secs = read_form(fields, PROFILE, model, today=date(2026, 10, 18))
        seconds.append(secs)
        for f, expected in page:
            rule_answer, key = by_rules[f["id"]]
            good, bad = score(rule_answer, expected)
            rules_ok += good
            rules_bad += bad
            llm = answers.get(f["id"], {})
            llm_answer = llm.get("answer") if llm.get("ok") and llm.get("answer") not in ("null", "") else None
            final = rule_answer if rule_answer is not None or key == "yes_no_question" else llm_answer
            good, bad = score(final, expected)
            hybrid_ok += good
            hybrid_bad += bad
            a = answers.get(f["id"], {"answer": None, "fact": None, "ok": True})
            answer = a["answer"]
            ok, _ = ground(f, answer, a.get("fact"), facts)
            given = answer not in (None, "", "null")
            if expected is None:
                good = not given
                invented += given
            else:
                good = given and ok and any(same(answer, e) for e in expected)
                blank += not given
            rejected += given and not ok
            correct += good
            rows.append((f["id"], f["label"][:50], answer, a.get("fact"), "ok" if good else "WRONG"))
    total = sum(len(p) for p in PAGES)
    return {"model": model, "correct": correct, "total": total, "invented": invented, "rejected": rejected,
            "blank": blank, "sec_per_page": sum(seconds) / len(seconds), "rows": rows,
            "rules_ok": rules_ok, "rules_bad": rules_bad, "hybrid_ok": hybrid_ok, "hybrid_bad": hybrid_bad}


if __name__ == "__main__":
    for model in sys.argv[1:] or ["qwen3:1.7b"]:
        r = run(model)
        print(f"\n=== {model}: {r['correct']}/{r['total']} correct, {r['invented']} invented (traps answered), "
              f"{r['rejected']} rejected by grounding, {r['blank']} left blank wrongly, {r['sec_per_page']:.0f} s/page")
        print(f"    rules alone: {r['rules_ok']}/{r['total']} ({r['rules_bad']} invented) | "
              f"rules + {model} for the rest: {r['hybrid_ok']}/{r['total']} ({r['hybrid_bad']} invented)")
        for row in r["rows"]:
            print(f"  {row[4]:5} {row[0]:4} {row[1]:52} -> {row[2]!r}  [{row[3]}]")
