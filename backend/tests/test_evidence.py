"""Yes/No questions answered from profile evidence.

The questions are deliberately worded in different ways: the point is that
the answer comes from WHAT is asked (topic + subject), not from exact wording.
"""

from datetime import date

import pytest

from agents.mapper import map_field
from services.evidence import answer_yes_no
from services.rules import YES_NO, classify

TODAY = date(2026, 10, 4)
PROFILE = {
    "education": {
        "degree": {"name": "B.Tech", "graduation_year": "2027", "graduation_month": "05"},
        "class_12": {"year": "2023", "month": "03"},
        "class_10": {"year": "2021", "month": "03"},
    },
    "languages_spoken": ["English", "Hindi", "Marathi", "German"],
    "skills": {"languages": ["Python", "Java", "SQL"], "ml_ai": ["TensorFlow/Keras", "scikit-learn"], "tools": ["Git"]},
    "projects": [{"title": "Smart Resume Scanner", "summary": "RAG pipeline with LangChain", "tech": ["Django", "LangChain"]}],
    "experience": [],
    "certifications": [{"name": "AWS Academy Graduate - Cloud Foundations"}],
}
GRADUATED = {**PROFILE, "education": {**PROFILE["education"], "degree": {"name": "B.Tech", "graduation_year": "2024", "graduation_month": "05"}}}


def ask(question, profile=PROFILE):
    a = answer_yes_no(question, profile, TODAY)
    return a.value, a.status


@pytest.mark.parametrize("question", [
    "Do you speak, write, and read fluently in English?",
    "Are you fluent in English?",
    "Can you communicate professionally in English?",
    "Is your English proficiency at a professional level?",
])
def test_language_paraphrases(question):
    assert ask(question) == ("Yes", "filled")


def test_language_not_in_profile_is_flagged_not_no():
    assert ask("Are you fluent in Japanese?") == (None, "review")


@pytest.mark.parametrize("question", [
    "Do you have a Bachelor's degree?",
    "Have you completed a B.Tech or equivalent?",
    "Do you hold an undergraduate degree?",
])
def test_degree_in_progress_is_never_claimed(question):
    value, status = ask(question)
    assert value is None and status == "review"


def test_degree_completed():
    assert ask("Do you have a Bachelor's degree?", GRADUATED) == ("Yes", "filled")


def test_higher_and_lower_levels():
    assert ask("Do you have a Master's degree?") == ("No", "review")
    assert ask("Have you completed Class 12 (higher secondary)?") == ("Yes", "filled")


@pytest.mark.parametrize("question,found", [
    ("Do you have experience with Python?", ("Yes", "filled")),
    ("Are you familiar with machine learning frameworks?", ("Yes", "review")),
    ("Do you have hands-on knowledge of LangChain?", ("Yes", "review")),
    ("Have you worked with SQL databases?", ("Yes", "filled")),
    ("Do you have experience with cloud platforms?", ("Yes", "review")),
])
def test_skill_paraphrases_with_evidence(question, found):
    assert ask(question) == found


@pytest.mark.parametrize("question", [
    "Do you have experience with Microsoft Office products and applications?",
    "Do you have experience with Excel?",
    "Are you proficient in Kubernetes?",
])
def test_skill_without_evidence_is_flagged_not_no(question):
    assert ask(question) == (None, "review")


def test_work_experience():
    assert ask("Have you had relevant non-internship professional experience?") == ("No", "review")
    with_job = {**PROFILE, "experience": [{"company": "Acme", "role": "ML Intern", "summary": "", "end": "2025-06"}]}
    assert ask("Have you completed an internship?", with_job) == ("Yes", "review")


def test_unknown_topic():
    assert ask("Are you willing to work night shifts?") == (None, "review")


def test_page_analyzer_and_mapper_route_yes_no():
    field = {"id": "q", "label": "Do you speak, write, and read fluently in English?", "kind": "select",
             "options": ["", "Yes", "No"], "placeholder": "", "helper_text": ""}
    assert classify(field) == YES_NO
    a = map_field(field, YES_NO, PROFILE)
    assert (a["value"], a["status"], a["source"]) == ("Yes", "filled", "evidence")
    bachelor = {**field, "label": "Do you have a Bachelor's degree?"}
    assert classify(bachelor) == YES_NO  # not degree.name any more
    # Profile answers stay direct: relocation is stored, not inferred.
    reloc = {**field, "label": "Are you willing to relocate?"}
    assert classify(reloc) == "preferences.willing_to_relocate"



@pytest.mark.parametrize("question", [
    "Are you currently employed?",
    "Are you currently partnered with any company?",
    "Are you presently associated with any organisation or serving a bond?",
    "Are you affiliated with any company at the moment?",
])
def test_not_currently_employed(question):
    assert ask(question) == ("No", "filled")


def test_currently_employed_is_yes_for_review():
    working = {**PROFILE, "experience": [{"company": "Acme", "role": "ML Intern", "start": "2026-06", "end": ""}]}
    assert ask("Are you currently employed?", working) == ("Yes", "review")


def test_previous_employer():
    assert ask("Have you ever worked for Infosys before?") == ("No", "filled")
    worked = {**PROFILE, "experience": [{"company": "Infosys", "role": "Intern", "start": "2025-05", "end": "2025-07"}]}
    assert ask("Have you previously been employed by Infosys?", worked) == ("Yes", "review")


def test_job_offer_comes_from_profile():
    assert ask("Are you already placed or holding any job offer?") == (None, "review")
    no_offer = {**PROFILE, "preferences": {"has_job_offer": "No"}}
    assert ask("Do you currently hold an offer letter from another company?", no_offer) == ("No", "filled")
