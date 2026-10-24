"""Citizenship / OCI / ex-employee Yes-No questions and 'foreign language' boxes (a real Deloitte form)."""

from agents.mapper import map_field
from services.rules import classify

PROFILE = {"personal": {"nationality": "Indian"}, "experience": [],
           "languages_spoken": ["English", "Hindi", "Marathi", "German"]}


def fill(label, kind="text", options=(), profile=PROFILE):
    d = {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}
    return map_field(d, classify(d), profile)


def test_real_form_questions_in_text_boxes():
    assert fill("Are you an Indian Citizen?")["value"] == "Yes"
    assert fill("Are you an Ex Employee of Deloitte?")["value"] == "No"
    oci = fill("If not an Indian citizen, Do you hold an OCI Card? (Y/N) - Example (Only if not an Indian Citizen but of Indian Origin)")
    assert oci["value"] == "No" and "OCI" in oci["reason"]


def test_same_questions_as_dropdowns():
    yn = ["Select", "Yes", "No"]
    assert fill("Are you an Indian Citizen?", "select", yn)["value"] == "Yes"
    assert fill("Do you hold citizenship or a passport of any country other than India?", "select", yn)["value"] == "No"


def test_foreign_language_excludes_english_and_indian_languages():
    assert fill("Additional Foreign Language known - Example ( French)")["value"] == "German"
    assert fill("Languages known")["value"] == "English, Hindi, Marathi, German"
    no_foreign = {**PROFILE, "languages_spoken": ["English", "Hindi"]}
    assert fill("Foreign language known", profile=no_foreign)["value"] is None


def test_unrelated_conditionals_and_detail_boxes_stay_yours():
    assert classify({"id": "x", "label": "If yes, please describe", "kind": "text", "options": []}) is None
    # Relatives are answered from the profile's Relatives list (added 2026-10-20); none saved -> yellow "Not applicable".
    relatives = fill("Do you have any relatives working here? If yes, give details")
    assert relatives["value"] == "Not applicable" and relatives["status"] == "review"
    assert classify({"id": "x", "label": "Nationality", "kind": "text", "options": []}) == "personal.nationality"
