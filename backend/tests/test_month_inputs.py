"""<input type="month"> boxes (IBM careers) only accept "YYYY-MM": never a bare year."""

from agents.mapper import map_field
from services.rules import classify

PROFILE = {"education": {"degree": {"name": "B.Tech", "start_year": "2023", "start_month": "06",
                                    "graduation_year": "2027", "graduation_month": "06"},
                         "class_12": {"year": "2023", "month": "01", "start_year": "2021", "start_month": "01"}}}


def month_box(label, section=""):
    return {"id": "x", "label": label, "kind": "month", "options": [], "placeholder": "", "helper_text": "", "section": section}


def fill(d):
    return map_field(d, classify(d), PROFILE)["value"]


def test_education_entry_from_to():
    assert fill(month_box("From", "Education")) == "2023-06"
    assert fill(month_box("To", "Education")) == "2027-06"


def test_year_questions_become_month_and_year():
    assert fill(month_box("Start year of degree")) == "2023-06"
    assert fill(month_box("Graduation year")) == "2027-06"
    assert fill(month_box("12th year of passing")) == "2023-01"


def test_year_in_a_text_box_stays_a_year():
    d = {**month_box("Graduation year"), "kind": "text"}
    assert fill(d) == "2027"
