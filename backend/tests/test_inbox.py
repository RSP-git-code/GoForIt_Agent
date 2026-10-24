"""Inbox agent on made-up placement emails written the way TPOs and companies write them."""

from datetime import date

from agents.inbox import process_email, process_inbox
from services.email_extract import extract_deadline, extract_eligibility, parse_date

PROFILE = {
    "education": {"degree": {"name": "B.Tech", "branch": "Computer Science and Engineering", "specialization": "AI and ML",
                             "graduation_year": "2027", "cgpa": "8.42", "active_backlogs": 0},
                  "class_12": {"percentage": "93.4"}, "class_10": {"percentage": "90.6"}},
    "skills": {"languages": ["Python", "SQL"], "ml_ai": ["scikit-learn", "TensorFlow/Keras", "LangChain"]},
    "projects": [{"title": "Smart Resume Scanner", "summary": "RAG pipeline", "tech": ["Python", "LangChain"]}],
}

TPO_DRIVE = {
    "id": "m1", "from": "Placement Cell <placements@college.example>", "date": "2026-10-05",
    "subject": "Campus Drive: Acme Analytics | Data Science Intern | 2027 Batch",
    "body": """Dear Students,

Acme Analytics is visiting campus for the 2027 batch.

Company: Acme Analytics
Role: Data Science Intern
Stipend: 40,000 per month

Eligibility:
- Branches: CSE, IT, ECE
- CGPA: 7.5 and above
- 10th and 12th: 70% and above
- No active backlogs

Skills: Python, SQL, machine learning, scikit-learn

Register here: https://forms.gle/AbCdEf123
Last date to register: 10/10/2026, 11:59 PM

Regards,
Training & Placement Office
https://www.facebook.com/college
""",
}

HIGH_CUTOFF = {
    "id": "m2", "from": "careers@bigbank.example", "date": "2026-10-05",
    "subject": "BigBank Hiring - Software Engineer (2027 graduates)",
    "body": """Hi,
BigBank is hiring Software Engineers.
Position: Software Engineer
Eligibility: CGPA 8.5 and above, CSE/IT only, 2027 passing out.
Apply on or before 15th October 2026 at https://bigbank.wd3.myworkdayjobs.com/en-US/careers/job/123
""",
}

OFF_CAMPUS = {
    "id": "m3", "from": "Unstop <noreply@unstop.example>", "date": "2026-10-05",
    "subject": "Off-campus opportunity: Gamma Labs ML Engineer Intern",
    "body": """Gamma Labs is hiring ML Engineer Interns. Work on LLM apps with LangChain and RAG.
Open to all branches. Deadline: Oct 20, 2026.
Apply: https://tally.so/r/abc123
Also see https://www.linkedin.com/jobs/view/999
Unsubscribe: https://unstop.example/unsubscribe?u=1""",
}

NOT_A_JOB = {
    "id": "m4", "from": "Swiggy <orders@swiggy.example>", "date": "2026-10-05",
    "subject": "Your order confirmed", "body": "Your order #123 is on the way. Track it here: https://swiggy.example/track/1",
}


def test_tpo_drive_email():
    row = process_email(TPO_DRIVE, PROFILE)
    assert row["company"] == "Acme Analytics"
    assert row["role"] == "Data Science Intern"
    assert row["deadline"] == "2026-10-10"
    assert row["apply_link"] == "https://forms.gle/AbCdEf123"  # facebook link dropped
    assert row["eligible"] == "Yes" and row["eligibility_notes"] == ""
    assert row["fit_score"] and "Python" in row["matched_skills"]


def test_cgpa_cutoff_makes_you_ineligible_with_reason():
    row = process_email(HIGH_CUTOFF, PROFILE)
    assert row["company"] == "BigBank" and row["role"] == "Software Engineer"
    assert row["deadline"] == "2026-10-15"
    assert row["eligible"] == "No" and "8.5" in row["eligibility_notes"]
    assert "myworkdayjobs" in row["apply_link"]


def test_off_campus_email():
    row = process_email(OFF_CAMPUS, PROFILE)
    assert row["company"] == "Gamma Labs"
    assert row["deadline"] == "2026-10-20"
    assert row["apply_link"] == "https://tally.so/r/abc123"
    assert "linkedin" in row["other_links"][-1]  # listed last, never opened
    assert all("unsubscribe" not in l for l in [row["apply_link"], *row["other_links"]])
    assert row["eligible"] == "Yes"
    assert "LangChain" in row["matched_skills"]


def test_non_job_emails_are_dropped():
    assert process_email(NOT_A_JOB, PROFILE) is None
    assert len(process_inbox([TPO_DRIVE, NOT_A_JOB, OFF_CAMPUS], PROFILE)) == 2


def test_date_formats():
    ref = date(2026, 10, 5)
    for text, expected in [
        ("10/10/2026", date(2026, 10, 10)),
        ("10-10-26", date(2026, 10, 10)),
        ("15th October 2026", date(2026, 10, 15)),
        ("Oct 20, 2026", date(2026, 10, 20)),
        ("25 Oct", date(2026, 10, 25)),
        ("2 Jan", date(2027, 1, 2)),  # no year and already past -> next year
    ]:
        assert parse_date(text, ref) == expected, text
    assert extract_deadline("Registration closes on 12.10.2026", "", ref) == date(2026, 10, 12)
    assert extract_deadline("No dates here", "", ref) is None


def test_eligibility_rules():
    rules = extract_eligibility("Eligible branches: CSE, ECE. Minimum CGPA of 7 required. 12th: 60% and above. 2026 and 2027 batch.")
    assert rules["min_cgpa"] == 7.0 and rules["min_12th"] == 60.0
    assert rules["branches"] == ["CSE", "ECE"] and rules["batches"] == [2026, 2027]
