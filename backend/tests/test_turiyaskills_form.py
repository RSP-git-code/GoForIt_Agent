"""Questions from real forms: Hitachi internship (Turiyaskills) and an 'Additional Info' form, 2026-10-09."""

import pytest

from agents.mapper import map_field
from services.rules import classify

PROFILE = {
    "personal": {"full_name": "Ananya Rao", "date_of_birth": "2005-06-13", "current_city": "Hyderabad",
                 "current_state": "Telangana", "permanent_city": "Nagpur", "permanent_state": "Maharashtra",
                 "nationality": "Indian"},
    "education": {"degree": {"name": "B.Tech", "cgpa": "8.42", "cgpa_scale": "10", "percentage_equivalent": "",
                             "graduation_year": "2027", "active_backlogs": 0}},
    "preferences": {"willing_to_relocate": "Yes", "preferred_locations": ["Hyderabad", "Pune"]},
    "standard_answers": {"about_me": "Final-year AI/ML student who builds RAG apps."},
}


def f(label, kind="text", options=None, placeholder=""):
    return {"id": "x", "label": label, "kind": kind, "options": options or [], "placeholder": placeholder, "helper_text": ""}


def fill(label, kind="text", options=None):
    field = f(label, kind, options)
    key = classify(field)
    return key, map_field(field, key, PROFILE)


@pytest.mark.parametrize("label,expected", [
    ("Current Course CGPA (Aggregated till date) - \"7/10 (if CGPA) 70 (If %)\"", "education.degree.cgpa"),
    ("Bachelor Percentage (if marks in CGPA, please convert to %)", "education.degree.percentage_equivalent"),
    ("Final Percentage (if marks in CGPA, please convert to %)", "education.degree.percentage_equivalent"),
    ("Final Year of Passing", "education.degree.graduation_year"),
    ("Bachelor Year of Passing", "education.degree.graduation_year"),
    ("Master Degree", "education.masters"),
    ("Master Percentage (if marks in CGPA, please convert to %)", "education.masters"),
    ("Master Year of Passing", "education.masters"),
    ("Master branch", "education.masters"),
    ("Master College", "education.masters"),
    ("If others, Please mention your Nationality", None),
    ("If Yes, do you require any assistance for the interview process", None),
    ("Current resident state", "personal.current_state"),
    ("Current resident city", "personal.current_city"),
    ("Permanent resident state", "personal.permanent_state"),
    ("Permanent resident city", "personal.permanent_city"),
    ("Hometown", "personal.permanent_city"),
    ("Profile Summary/Highlights", "standard_answers.about_me"),
    ("10th Percentage (if marks in CGPA, please convert to %)", "education.class_10.percentage"),
])
def test_classification(label, expected):
    assert classify(f(label)) == expected


def test_backlogs_as_yes_no():
    key, a = fill("Standing Backlog / Arrears (If Any)", "radio", ["a. Yes", "b. No"])
    assert key == "education.degree.active_backlogs" and (a["value"], a["status"]) == ("b. No", "filled")


def test_open_to_any_location_uses_relocation_answer():
    key, a = fill("Are you open for any location across India", "radio", ["a. Yes", "b. No"])
    assert key == "preferences.willing_to_relocate" and a["value"] == "a. Yes"


def test_values():
    assert fill("Date of Birth (YYYY/MM/DD)")[1]["value"] == "2005/06/13"
    assert fill("Date of Birth (YYYY-MM-DD)")[1]["value"] == "2005-06-13"
    assert fill("Date of Birth")[1]["value"] == "13/06/2005"
    assert fill("Current Course CGPA (Aggregated till date)")[1]["value"] == "8.42"
    pct = fill("Bachelor Percentage (if marks in CGPA, please convert to %)")[1]
    assert pct["status"] == "missing" and pct["value"] is None  # never sends the CGPA as a percentage
    assert fill("Master Degree")[1]["status"] == "skipped"
    assert fill("Permanent resident city")[1]["value"] == "Nagpur"
    assert fill("Profile Summary/Highlights", "textarea")[1]["value"].startswith("Final-year")



@pytest.mark.parametrize("label", [
    "Profile Summary/Highlight", "Profile Summary/Highlights", "Highlights", "Key Highlights",
    "Profile Highlights", "Professional Summary", "Career Summary", "Brief Profile", "Career Objective",
    "Summary about yourself", "Tell us about yourself", "About Me", "Highlights & Summary",
])
def test_every_way_of_asking_for_a_summary(label):
    assert classify(f(label, "textarea")) == "standard_answers.about_me"


def test_summary_is_written_from_profile_when_about_me_is_empty():
    no_summary = {**PROFILE, "standard_answers": {"about_me": ""},
                  "education": {"degree": {"name": "B.Tech", "branch": "Computer Science and Engineering",
                                           "college": "Example Institute", "graduation_year": "2027"}},
                  "skills": {"languages": ["Python", "SQL"], "ml_ai": ["LangChain"]},
                  "projects": [{"title": "Smart Resume Scanner", "summary": "Built a RAG resume matcher. More text.", "tech": []}]}
    a = map_field(f("Profile Summary/Highlights", "textarea"), "standard_answers.about_me", no_summary)
    assert a["status"] == "review" and "Written from your profile" in a["reason"]
    assert "B.Tech" in a["value"] and "Python, SQL, LangChain" in a["value"] and "Smart Resume Scanner" in a["value"]
    assert "Example Institute" in a["value"]
