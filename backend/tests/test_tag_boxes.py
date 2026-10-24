"""Skills boxes that turn each entry into a tag must not get the whole list typed in."""

from agents.mapper import map_field, top_skills
from services.rules import classify

PROFILE = {"skills": {"languages": ["Python", "Java", "C", "C++", "Bash Scripting"],
                      "ml_ai": ["scikit-learn", "TensorFlow/Keras", "Pandas", "NumPy", "LangChain"],
                      "web": ["Django", "HTML", "CSS"], "databases": ["PostgreSQL", "SQL"], "tools": ["Git"]}}


def f(label, helper="", section="", kind="text"):
    return {"id": "x", "label": label, "helper_text": helper, "section": section, "kind": kind, "options": [], "placeholder": ""}


def test_workday_type_to_add_skills_goes_in_as_tags():
    # The extension adds each skill from the site's suggestions (never the whole list typed, never Enter).
    d = f("Type to Add Skills", section="Skills")
    a = map_field(d, classify(d), PROFILE)
    assert a["mode"] == "tags" and a["status"] == "review"
    assert a["value"][:3] == ["Python", "scikit-learn", "Django"] and len(a["value"]) == 12


def test_tag_box_respects_choose_up_to_n():
    d = f("Skills (choose up to 3)", kind="combobox")
    assert map_field(d, classify(d), PROFILE)["value"] == ["Python", "scikit-learn", "Django"]


def test_press_enter_hint_and_combobox_count_as_tag_boxes():
    for d in (f("Skills", helper="Please make sure to click ENTER once you have typed in your skills."),
              f("Skills", kind="combobox")):
        assert map_field(d, classify(d), PROFILE)["mode"] == "tags"


def test_plain_skills_box_still_gets_the_list():
    d = f("Technical skills")
    assert map_field(d, classify(d), PROFILE)["value"].startswith("Python, Java")


def test_top_skills_is_balanced_and_capped():
    top = top_skills(PROFILE)
    assert len(top) == 12 and top[:5] == ["Python", "scikit-learn", "Django", "PostgreSQL", "Git"]
