"""Language + Proficiency dropdowns (Globant form), and sensitive questions that are never filled or drafted."""

from agents.graph import draftable, run_fill
from agents.mapper import language_and_level, mapper
from services.rules import classify

LANGS = ["No Selection", "English", "French", "German", "Hindi", "Spanish"]
LEVELS = ["No Selection", "Basic", "Intermediate", "Advanced", "Native or bilingual"]


def f(i, label, kind="select", options=(), section=""):
    return {"id": f"f{i}", "label": label, "kind": kind, "options": list(options), "section": section,
            "placeholder": "", "helper_text": ""}


def plan(fields, profile):
    classified = [{"field_id": d["id"], "key": classify(d)} for d in fields]
    return {a["field_id"]: a for a in mapper({"fields": fields, "classified": classified, "profile": profile})["fill_plan"]}


def test_language_then_proficiency_uses_that_languages_level():
    profile = {"languages_spoken": ["English (Fluent)", "Hindi (Native)", "German (Basic)"]}
    p = plan([f(0, "Language *", options=LANGS, section="Languages"), f(1, "Proficiency *", options=LEVELS, section="Languages")], profile)
    assert p["f0"]["value"] == "English" and "Add" in p["f0"]["reason"]
    assert p["f1"]["value"] == "Advanced"           # "Fluent" -> closest option


def test_proficiency_without_a_saved_level_is_left_for_you():
    p = plan([f(0, "Language", options=LANGS), f(1, "Proficiency", options=LEVELS)], {"languages_spoken": ["English", "Hindi"]})
    assert p["f0"]["value"] == "English"
    assert p["f1"]["value"] is None and "English (Fluent)" in p["f1"]["reason"]


def test_language_entries_with_levels_still_work_elsewhere():
    assert language_and_level("Hindi (Native)") == ("Hindi", "Native")
    assert language_and_level("German - Basic") == ("German", "Basic")
    assert language_and_level("Marathi") == ("Marathi", "")


def test_sensitive_questions_are_never_filled_or_drafted():
    profile = {"standard_answers": {"about_me": "Fourth-year student."}}
    for label in ("Additional information about accessibility?", "Do you require any accommodations during the interview?",
                  "Do you have a disability?", "Any medical condition we should know about?"):
        field = f(0, label, kind="textarea")
        assert classify(field) is None, label
        result = run_fill([field], profile, None)
        assert result["actions"][0]["value"] is None and draftable([field], result["actions"]) == [], label


def test_levels_dont_break_other_language_answers():
    from agents.mapper import map_field
    from services.evidence import answer_yes_no
    profile = {"languages_spoken": ["English (Fluent)", "Hindi (Native)", "German (Basic)"]}
    assert answer_yes_no("Do you speak English fluently?", profile).value == "Yes"
    d = f(0, "Additional Foreign Language known - Example (French)", kind="text")
    assert map_field(d, classify(d), profile)["value"] == "German"


def test_a_real_question_label_wins_over_a_copied_placeholder():
    # Same mistake on a non-sensitive question: the placeholder must not turn it into "about me".
    d = {"id": "x", "label": "Additional information about your availability?", "kind": "textarea", "options": [],
         "placeholder": "Tell us a little bit about yourself", "helper_text": ""}
    assert classify(d) != "standard_answers.about_me"
    # The Globant case itself, with its Yes/No question above it: nothing filled.
    yes_no = f(0, "Do you need any adaptation in terms of accessibility such as subtitles, facilitating lip reading, or any other?",
               kind="checkbox", options=["No", "Yes", "I prefer not to answer"], section="Accessibility")
    box = {**d, "id": "f1", "label": "Additional information about accessibility?", "section": "Accessibility"}
    p = plan([yes_no, box], {"standard_answers": {"about_me": "Fourth-year student."}})
    assert p["f0"]["value"] is None and p["f1"]["value"] is None
    # Short, vague labels still use the placeholder / name (e.g. Greenhouse's name="urls[GitHub]").
    assert classify({"id": "y", "label": "Other", "kind": "text", "options": [], "name": "urls[GitHub]",
                     "placeholder": "", "helper_text": ""}) == "links.github"


def test_experience_in_x_comes_from_projects_and_skills():
    from agents.mapper import map_field
    profile = {"skills": {"languages": ["Python", "Java"], "ml_ai": ["scikit-learn", "LangChain", "Google Gemini API"]},
               "projects": [{"title": "Smart Resume Scanner - RAG-based matching", "summary": "Django app with a RAG pipeline.",
                             "tech": ["Python", "Django", "LangChain", "RAG", "Gemini API"]},
                            {"title": "Disaster Management Predictor", "summary": "Risk prediction.",
                             "tech": ["Python", "scikit-learn", "Plotly"]}],
               "experience": []}

    def ans(label):
        d = {"id": "x", "label": label, "kind": "text", "options": [], "placeholder": "Your answer", "helper_text": "", "max_length": 500}
        return map_field(d, classify(d), profile)
    py = ans("Hands on experience in Python?")
    assert py["status"] == "review" and "Smart Resume Scanner (Python)" in py["value"] and "Disaster Management Predictor" in py["value"]
    llm = ans("Hands on experience in LLM APIs")
    assert "LangChain" in llm["value"] and "Gemini API" in llm["value"]
    aiml = ans("How much experience you hold in AI/ML?")
    assert aiml["value"].startswith("No industry experience yet") and "scikit-learn" in aiml["value"]
    assert ans("Hands on experience in Kubernetes?")["value"] is None    # not in the profile: never invented
    assert classify({"id": "y", "label": "Years of experience in Python", "kind": "text", "options": []}) == "experience.total_years"


def test_hsbc_successfactors_questions():
    from agents.mapper import map_field
    profile = {"personal": {"gender": "Female", "nationality": "Indian"}, "experience": [],
               "preferences": {"work_authorization_india": "Yes"}}

    def ans(label, kind="combobox", options=()):
        d = {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}
        return map_field(d, classify(d), profile)
    assert ans("Gender (As shown on your national ID)")["value"] == "Female"
    assert ans("Are you eligible to work in the country / territory where this role is based?")["value"] == "Yes"
    auditors = ans("Have you been employed, or are still employed, by HSBC's external auditors? You may be asked "
                   "to disclose more information during the recruitment process if the answer is Yes")
    assert auditors["value"] == "No" and len(auditors["reason"]) < 60
    assert ans("Country/Territory:", "select", ["- Select -", "India", "United Kingdom"])["value"] == "India"
    for left in ("What is your ethnic group?", "Diversity and Inclusion Consent",
                 "Do you have a disability (including physical or sensory)? Long term / mental health condition?"):
        assert ans(left)["value"] is None, left


def test_relatives_at_the_company():
    from agents.form_reader import profile_facts
    from services.profile_facts import safe_profile
    family = {"relatives": [{"company": "Franklin Templeton", "relation": "Father", "name": "A. Example",
                             "job_title": "Analyst", "department": "Operations", "location": "Hyderabad"}]}
    yn = ["Select", "Yes", "No"]

    def ans(label, profile, kind="select", options=yn):
        d = {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}
        return map_field(d, classify(d), profile)
    from agents.mapper import map_field
    q = "Do you have any relatives working within HSBC group?"
    details = ("If you have any relative working with HSBC group, please provide name & additional information "
               "such as location, job title, department etc.")
    assert ans(q, family)["value"] == "No"
    assert ans(details, family, "textarea", ())["value"] == "Not applicable"
    assert ans("Do you have any relatives working at Franklin Templeton?", family)["value"] == "Yes"
    assert ans("If you have any relative working with Franklin Templeton, please provide name and details",
               family, "textarea", ())["value"] == "A. Example (Father), Analyst, Operations, Hyderabad"
    # Nothing saved: "No" but yellow, so you check it.
    a = ans(q, {})
    assert a["value"] == "No" and a["status"] == "review"
    # Never shown to the AI agents: it's about other people.
    assert not any(k.startswith("relatives") for k in profile_facts(family))
    assert "relatives" not in safe_profile(family)


def test_optional_diversity_answers():
    from agents.form_reader import profile_facts
    from agents.mapper import map_field
    saved = {"diversity": {"consent": "Yes", "ethnicity": "Asian - Indian Subcontinent", "disability": "No", "veteran": ""}}

    def ans(label, profile, kind="combobox", options=()):
        d = {"id": "x", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}
        return map_field(d, classify(d), profile)
    assert ans("Diversity and Inclusion Consent", saved)["value"] == "Yes"
    assert ans("Do you have a disability (including physical or sensory)? Long term / mental health condition?", saved)["value"] == "No"
    eth = ans("What is your ethnic group?", saved)
    assert eth["value"][0] == "Asian - Indian Subcontinent" and "Indian" in eth["value"]   # alternatives for site dropdowns
    uk = ans("What is your ethnic group?", saved, "select", ["Select", "White", "Asian or Asian British - Indian"])
    assert uk["value"] == "Asian or Asian British - Indian" and uk["status"] == "review"
    # Nothing saved: left for you. Free-text accessibility questions: always left for you.
    assert ans("What is your ethnic group?", {})["value"] is None
    assert ans("Additional information about accessibility?", saved, "textarea")["value"] is None
    assert not any(k.startswith("diversity") for k in profile_facts(saved))   # never shown to the AI
