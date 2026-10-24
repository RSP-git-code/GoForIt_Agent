"""'Start of Course' / 'End of Course' date pickers with an example placeholder."""

from agents.mapper import map_field
from services.rules import classify

PROFILE = {"education": {"degree": {"name": "B.Tech", "start_year": "2023", "start_month": "06",
                                    "graduation_year": "2027", "graduation_month": "06"}}}


def f(label, placeholder=""):
    return {"id": "x", "label": label, "placeholder": placeholder, "kind": "text", "options": [], "helper_text": "", "section": ""}


def test_course_start_and_end_are_degree_dates():
    assert classify(f("Start of Course")) == "education.degree.start_date"
    assert classify(f("End of Course")) == "education.degree.graduation_date"
    assert classify(f("Course completion date")) == "education.degree.graduation_date"
    assert classify(f("Year of completion of the degree")) is not None
    assert classify(f("Course")) != "education.degree.start_date"


def test_example_placeholder_gets_the_same_style():
    d = f("Start of Course", "16 June 2014")
    a = map_field(d, classify(d), PROFILE)
    assert a["value"] == "1 June 2023" and a["status"] == "review" and "1st" in a["reason"]
    d = f("End of Course", "16 Jul 2018")
    assert map_field(d, classify(d), PROFILE)["value"] == "1 Jun 2027"


def test_dd_mm_yyyy_hint_gets_a_full_date():
    d = f("End of Course", "DD/MM/YYYY")
    assert map_field(d, classify(d), PROFILE)["value"] == "01/06/2027"


def test_dob_with_example_placeholder():
    d = {**f("Date of Birth", "16 June 2014")}
    a = map_field(d, classify(d), {"personal": {"date_of_birth": "2004-01-15"}})
    assert a["value"] == "15 January 2004"
