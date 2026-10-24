"""Saved work-authorization answers are for India; foreign-country questions are left to you."""

from agents.mapper import map_field
from services.rules import classify

PROFILE = {"preferences": {"work_authorization_india": "Yes", "requires_sponsorship": "No"}}


def q(label, options=("Yes", "No")):
    return {"id": "x", "label": label, "kind": "select", "options": list(options), "placeholder": "", "helper_text": ""}


def test_india_and_unnamed_country_use_the_profile():
    for label in ("Are you legally authorized to work in India?",
                  "Are you legally authorized to work in the country in which this job is located?"):
        d = q(label)
        assert classify(d) == "preferences.work_authorization_india"
        assert map_field(d, classify(d), PROFILE)["value"] == "Yes"


def test_foreign_country_is_not_answered_from_the_india_profile():
    for label in ("Are you legally authorized to work in the United States?",
                  "Are you currently authorized to work in the U.S.?",
                  "Are you legally authorized to work in Singapore?",
                  "Will you now or in the future require sponsorship for employment visa status (e.g., H-1B visa status)?",
                  "Do you, now or in the future, require sponsorship to work in the United States?"):
        d = q(label)
        key = classify(d)
        assert key not in ("preferences.work_authorization_india", "preferences.requires_sponsorship"), label
        assert map_field(d, key, PROFILE)["status"] != "filled", label


def test_us_pronoun_is_not_a_country():
    assert classify(q("Will you require us to sponsor your visa?")) == "preferences.requires_sponsorship"
