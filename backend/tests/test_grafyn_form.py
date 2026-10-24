"""Questions from a real campus Google Form (Grafyn AI, 2026-10-08)."""

from datetime import date

import pytest

from agents.drafter import write_draft
from agents.mapper import map_field
from services.rules import classify

PROFILE = {
    "personal": {"full_name": "Ananya Rao", "email": "a@gmail.example", "college_email": "ananya@college.example"},
    "links": {"resume_link": "https://drive.google.com/file/d/abc/view"},
    "education": {
        "degree": {"name": "B.Tech", "branch": "Computer Science and Engineering", "college": "Example Institute",
                   "graduation_year": "2027", "graduation_month": "05", "cgpa": "8.5"},
        "class_10": {"percentage": "92"},
        "class_12": {"percentage": "94", "board": "TSBIE", "math_percentage": "97"},
        "entrance_exams": {"jee_main_percentile": "96.2", "jee_main_rank": "45000", "jee_advanced_rank": "NA"},
    },
    "skills": {"languages": ["Python", "Java", "C", "C++", "SQL"], "ml_ai": ["scikit-learn", "TensorFlow", "Keras", "LangChain", "RAG", "Pandas"]},
    "experience": [],
    "achievements": ["Research Team Co-Lead, Data Science Club"],
}


def f(label, kind="text", options=None):
    return {"id": "x", "label": label, "kind": kind, "options": options or [], "placeholder": "", "helper_text": ""}


def fill(label, kind="text", options=None):
    field = f(label, kind, options)
    key = classify(field)
    return key, map_field(field, key, PROFILE)


@pytest.mark.parametrize("label,expected", [
    ("Your Institute Email ID", "personal.college_email"),
    ("Personal Email ID", "personal.email"),
    ("Name of Current/Last Institution", "education.degree.college"),
    ("GPA so far", "education.degree.cgpa"),
    ("Grade-X GPA/Percentage", "education.class_10.percentage"),
    ("Grade-XII Board Name", "education.class_12.board"),
    ("Grade-XII GPA/Percentage", "education.class_12.percentage"),
    ("Grade-XII Math GPA/Percentage (mention NA, if not applicable)", "subject_marks"),
    ("If yes, please share the link to the certificate (Google Drive or OneDrive link with anonymous access)", None),
    ("Please share your resume (max one page) Note: please upload to Google Drive or OneDrive and share the link", "links.resume_link"),
])
def test_classification(label, expected):
    assert classify(f(label)) == expected


def test_values():
    assert fill("Your Institute Email ID")[1]["value"] == "ananya@college.example"
    assert fill("Name of Current/Last Institution")[1]["value"] == "Example Institute"  # never your own name
    assert fill("Grade-XII Math GPA/Percentage (mention NA, if not applicable)")[1]["value"] == "97"
    assert fill("JEE Main Percentile and Rank (mention NA if not applicable)")[1]["value"] == "96.2 percentile, Rank 45000"
    assert fill("JEE Advanced Percentile and Rank (mention NA if not applicable)")[1]["value"] == "NA"
    assert fill("Please share your resume (max one page) Note: upload to Google Drive and share the link")[1]["value"].startswith("https://drive")


def test_qualification_dropdowns():
    key, a = fill("Highest Educational Qualification", "select", ["B.Tech (Computer Science)", "MCA"])
    assert key == "education.degree.name" and a["value"] == "B.Tech (Computer Science)"
    key, a = fill("Highest Educational Qualification - In Progress/Completed?", "select", ["In Progress", "Completed"])
    assert key == "education.degree.status"
    assert a["value"] == ("In Progress" if date.today() < date(2027, 5, 1) else "Completed")


def test_year_not_listed_picks_other():
    _, a = fill("Year of Completion/Graduation", "select", ["2024", "2025", "2026", "Other"])
    assert (a["value"], a["status"]) == ("Other", "review")


def test_lists_and_experience():
    _, skills = fill("Skills (list up to 10)", "textarea")
    assert len(skills["value"].split(", ")) == 10 and skills["status"] == "review"
    _, exp = fill("Prior Internship/Work Experience", "textarea")
    assert exp["value"] == "No prior internship or work experience." and exp["status"] == "review"
    key, comp = fill("Have you won any coding competitions? You can mention your achievements on LeetCode", "textarea")
    assert key == "achievements" and comp["status"] == "review"
    key, _ = fill("Extracurricular activities you have interests in? (max 2-3 lines)", "textarea")
    assert key == "achievements"


def test_video_link_question_gets_no_text_draft():
    label = "What excites you about Grafyn AI for the role? Please record a max 60 seconds video. Upload it to Google Drive and share the link below."
    assert write_draft(f(label, "textarea"), {"profile": PROFILE})["text"] == ""
