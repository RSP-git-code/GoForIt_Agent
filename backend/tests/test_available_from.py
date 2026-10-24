"""'When can you start?' from preferences.available_from; Student / NA when there's no experience."""

from datetime import date
from unittest.mock import patch

from agents import mapper
from agents.mapper import available_from, map_field
from services.rules import classify

SAVED = "2026-11-23"  # free after the capstone review


def f(label, kind="text", options=(), placeholder=""):
    return {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": placeholder, "helper_text": ""}


def prof(available=SAVED, notice="0"):
    return {"preferences": {"available_from": available, "notice_period": notice}, "experience": []}


def on(day: str, *args):
    """available_from(...) as if today were `day`."""
    class Today(date):
        @classmethod
        def today(cls):
            return date.fromisoformat(day)
    with patch.object(mapper, "date", Today):
        return available_from(*args)[0]


def test_start_questions_are_recognised():
    for label in ("When are you available to start?", "How soon are you available to start?", "Earliest joining date",
                  "When can you join?", "Date of joining"):
        assert classify(f(label)) == "preferences.available_from", label
    assert classify(f("Notice period")) == "preferences.notice_period"


def test_october_says_the_month_november_says_immediately():
    assert on("2026-10-11", prof(), f("When can you join?")) == "November 2026"
    assert on("2026-10-31", prof(), f("When can you join?")) == "November 2026"
    assert on("2026-11-01", prof(), f("When can you join?")) == "Immediately"
    assert on("2026-12-15", prof(), f("When can you join?")) == "Immediately"
    assert "November 2026" in on("2026-10-11", prof(), f("How soon are you available to start?"))


def test_exact_date_boxes():
    assert on("2026-10-11", prof(), f("Joining date", kind="date")) == "2026-11-01"
    assert on("2026-11-05", prof(), f("Joining date", kind="date")) == "2026-11-05"
    assert on("2026-10-11", prof(), f("Joining date", placeholder="DD/MM/YYYY")) == "01/11/2026"


def test_empty_date_uses_notice_period():
    assert on("2026-10-11", prof(""), f("When can you start?")) == "Immediately"   # notice period 0
    assert on("2026-10-11", prof("", notice=""), f("When can you start?")) is None  # nothing saved: ask you


def test_dropdowns():
    options = ["Immediately", "Within 2 weeks", "Less than 30 days", "Between 30-60 days", "60+ days"]
    assert on("2026-10-11", prof(), f("When can you start?", "select", options)) == "Less than 30 days"
    assert on("2026-11-02", prof(), f("When can you start?", "select", options)) == "Immediately"
    months = ["October", "November", "December", "January"]
    assert on("2026-10-11", prof(), f("Which month can you join?", "select", months)) == "November"


def test_no_experience_gives_student_and_na():
    p = {"experience": []}
    d = f("What is your current job title?")
    assert classify(d) == "experience.current_title" and map_field(d, classify(d), p)["value"] == "Student"
    d = f("Current company name")
    assert map_field(d, classify(d), p)["value"] == "NA"
    assert classify(f("Job Title")) != "experience.current_title"   # Workday's experience entry: left alone


def test_mm_yyyy_box_gets_month_slash_year():
    # HCLTech "When are you available to join?" box shows "10/2026" style (MM/YYYY).
    box = f("When are you available to join?", placeholder="MM/YYYY")
    assert on("2026-10-20", prof("2026-12-05"), box) == "12/2026"
    assert on("2027-01-10", prof("2026-12-05"), box) == "01/2027"   # date has passed: this month
