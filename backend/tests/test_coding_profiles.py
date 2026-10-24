"""Coding platform questions, the profile link after them, and achievements that fit the question."""

from agents.mapper import mapper, map_field
from services.rules import classify

PROFILE = {
    "links": {"leetcode": "https://leetcode.com/u/me/", "github": "https://github.com/me",
              "other": ["CodeChef:https://www.codechef.com/users/me"]},
    "achievements": ["Research Team Co-Lead, Data Science Club (Sep 2024 - Oct 2025)",
                     "Certificate of Appreciation, Data Science Club (Jun 2025)",
                     "GFG Hacktoberfest participant (Oct 2023)"],
}
PLATFORMS = ["LeetCode", "Codeforces", "CodeChef", "HackerRank", "GeeksforGeeks", "Other", "Not Registered"]


def f(i, label, kind="text", options=()):
    return {"id": f"f{i}", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}


def run(fields, profile=PROFILE):
    classified = [{"field_id": d["id"], "key": classify(d)} for d in fields]
    plan = mapper({"fields": fields, "classified": classified, "profile": profile})["fill_plan"]
    return {a["field_id"]: a for a in plan}


def test_platform_then_profile_link_uses_context():
    # The real form: platform choice, rating, then a generic "Profile / Evidence Link".
    plan = run([f(0, "Coding Platform", "radio", PLATFORMS), f(1, "Coding Rating / Rank - Example (1850)"),
                f(2, "Profile / Evidence Link - (Profile URL)")])
    assert plan["f0"]["value"] == "LeetCode"
    assert plan["f1"]["value"] is None                      # no rating saved: left for you
    assert plan["f2"]["value"] == "https://leetcode.com/u/me/" and "LeetCode" in plan["f2"]["reason"]


def test_link_follows_the_platform_that_was_picked():
    only_codechef = {**PROFILE, "links": {"other": ["CodeChef:https://www.codechef.com/users/me"]}}
    plan = run([f(0, "Coding Platform", "radio", PLATFORMS), f(1, "Profile / Evidence Link")], only_codechef)
    assert plan["f0"]["value"] == "CodeChef" and plan["f1"]["value"] == "https://www.codechef.com/users/me"


def test_profile_link_without_a_platform_question_is_not_guessed():
    assert run([f(0, "Profile / Evidence Link")])["f0"]["value"] is None


def test_checkbox_platforms_tick_every_saved_one():
    plan = run([f(0, "Coding platforms you use", "checkbox", PLATFORMS)])
    assert set(plan["f0"]["value"]) == {"LeetCode", "CodeChef"}


def test_one_line_box_gets_only_the_relevant_achievement():
    d = f(0, "Hackathon / Competition Details - Example (Smart India Hackathon)")
    a = map_field(d, classify(d), PROFILE)
    assert a["value"] == "GFG Hacktoberfest participant (Oct 2023)"
    d = f(0, "Hackathon / Competition Achievement - Example (Finalist)")
    assert map_field(d, classify(d), PROFILE)["value"] == "Participant"


def test_no_matching_achievement_leaves_it_for_you():
    p = {"achievements": ["Research Team Co-Lead, Data Science Club"]}
    d = f(0, "Hackathon / Competition Details")
    a = map_field(d, classify(d), p)
    assert a["value"] is None and a["status"] == "review"


def test_achievements_text_area_keeps_the_list():
    d = f(0, "Achievements", "textarea")
    assert map_field(d, classify(d), PROFILE)["value"].count("\n") == 2
