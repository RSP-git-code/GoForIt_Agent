"""Matcher, template Drafter and Verifier, plus relocation / experience / education answers."""

from agents.drafter import company_from, write_draft
from agents.graph import run_fill
from agents.mapper import map_field
from agents.matcher import match
from agents.verifier import check_draft
from services.profile_facts import safe_profile
from services.rules import classify

PROFILE = {
    "personal": {"full_name": "Ananya Rao", "email": "secret@example.com", "phone": "+91 9000012345",
                 "permanent_address": "Flat 1, Some Road", "current_city": "Hyderabad"},
    "education": {"degree": {"name": "B.Tech", "branch": "Computer Science and Engineering", "specialization": "AI and ML",
                             "college": "Example Institute", "graduation_year": "2027", "cgpa": "8.5", "cgpa_scale": "10"},
                  "class_12": {"school": "Example Junior College", "board": "TSBIE", "year": "2023", "percentage": "94"},
                  "class_10": {"school": "Example School", "board": "CBSE", "year": "2021", "percentage": "92"}},
    "skills": {"languages": ["Python", "SQL"], "ml_ai": ["scikit-learn", "LangChain", "Stable-Baselines3"]},
    "projects": [
        {"title": "Smart Resume Scanner", "summary": "Built a RAG pipeline that matches resumes to job descriptions. Uses Chroma.",
         "tech": ["Python", "LangChain", "RAG"], "link": "https://github.com/x/srs"},
        {"title": "Satellite Power Optimization", "summary": "Trained a PPO agent for satellite power modes.",
         "tech": ["Python", "Gymnasium", "Stable-Baselines3"], "link": ""},
    ],
    "experience": [],
    "certifications": [{"name": "Neural Networks and Deep Learning", "issuer": "DeepLearning.AI"}],
    "preferences": {"willing_to_relocate": "", "preferred_locations": ["Bengaluru", "Pune"]},
}


def f(label, kind="text", **extra):
    return {"id": "x", "label": label, "kind": kind, "options": [], "placeholder": "", "helper_text": "", **extra}


# ---------- safety ----------

def test_agents_never_see_contact_details():
    text = str(safe_profile(PROFILE))
    for secret in ("secret@example.com", "9000012345", "Flat 1", "Ananya"):
        assert secret not in text


# ---------- Matcher ----------

def test_matcher_picks_the_project_that_fits_the_job():
    rl_job = "We build reinforcement learning agents with Stable-Baselines3 and Gymnasium for robots."
    assert match(rl_job, PROFILE)["best_projects"][0]["title"] == "Satellite Power Optimization"
    llm_job = "Build LLM apps with LangChain and RAG over company documents."
    fit = match(llm_job, PROFILE)
    assert fit["best_projects"][0]["title"] == "Smart Resume Scanner"
    assert "LangChain" in fit["matched_skills"] and fit["score"] > 0


# ---------- Drafter ----------

def test_company_name_from_question():
    assert company_from("Why would you like to join RingTrunk?", "") == "RingTrunk"
    assert company_from("Why do you want to work with us?", "") is None


def test_motivation_draft_uses_only_profile_facts():
    state = {"profile": PROFILE, "fit": match("LLM apps with LangChain and RAG", PROFILE), "retries": {}}
    draft = write_draft(f("Why would you like to join RingTrunk?", "textarea"), state)
    text = draft["text"]
    assert draft["kind"] == "motivation"
    assert "RingTrunk" in text and "Smart Resume Scanner" in text and "B.Tech" in text
    assert check_draft(draft, f("Why?", "textarea"), state)["passed"]


def test_project_draft_and_length_limit():
    state = {"profile": PROFILE, "fit": None, "retries": {}}
    full = write_draft(f("Tell us about your best project", "textarea"), state)["text"]
    assert full.startswith("Smart Resume Scanner:") and "Tech used" in full
    short = write_draft(f("Describe a project you are proud of", "textarea", max_length=120), state)["text"]
    assert 0 < len(short) <= 120


def test_unknown_question_gets_no_draft():
    assert write_draft(f("Anything else we should know?", "textarea"), {"profile": PROFILE})["text"] == ""


# ---------- Verifier ----------

def test_verifier_catches_invented_facts():
    state = {"profile": PROFILE}
    bad_number = check_draft({"text": "I scored a CGPA of 9.8 in my B.Tech."}, f("Why?"), state)
    assert not bad_number["passed"] and "9.8" in bad_number["reasons"][0]
    bad_skill = check_draft({"text": "I have built Kubernetes clusters with Docker."}, f("Why?"), state)
    assert not bad_skill["passed"] and "kubernetes" in bad_skill["reasons"][0]
    too_long = check_draft({"text": "x" * 50}, f("Why?", max_length=20), state)
    assert not too_long["passed"]
    assert check_draft({"text": "I built Smart Resume Scanner with Python and LangChain."}, f("Why?"), state)["passed"]


def test_full_pipeline_drafts_the_motivation_question():
    fields = [{"id": "q", "label": "Why would you like to join RingTrunk?", "kind": "textarea", "options": []}]
    r = run_fill(fields, PROFILE, "We use Python, LangChain and RAG to build assistants.")
    a = r["actions"][0]
    assert a["status"] == "review" and a["source"] == "draft" and "RingTrunk" in a["value"]
    assert r["fit"]["best_projects"][0]["title"] == "Smart Resume Scanner"


# ---------- relocation, experience, education ----------

def reloc(label, profile=PROFILE, options=("Yes", "No")):
    field = f(label, "radio", options=list(options))
    return map_field(field, classify(field), profile)


def test_relocation_from_preferred_locations():
    a = reloc("Are you willing to relocate to Bengaluru?")
    assert (a["value"], a["status"]) == ("Yes", "review") and "Bengaluru" in a["reason"]  # inferred, so shown with its reason
    other = reloc("Are you willing to relocate to Chennai?")
    assert other["value"] is None and other["status"] == "review"
    saved = {**PROFILE, "preferences": {"willing_to_relocate": "Yes", "preferred_locations": []}}
    assert reloc("Willing to relocate anywhere in India?", saved)["value"] == "Yes"


def test_total_experience():
    fresher = map_field(f("Experience (in years)", "number"), "experience.total_years", PROFILE)
    assert (fresher["value"], fresher["status"]) == ("0", "filled")
    assert classify(f("Experience (in years)", "number")) == "experience.total_years"
    assert classify(f("Total years of experience")) == "experience.total_years"
    dropdown = f("Years of experience", "select", options=["Select", "Fresher", "1-2 years", "3+ years"])
    assert map_field(dropdown, classify(dropdown), PROFILE)["value"] == "Fresher"
    worked = {**PROFILE, "experience": [{"company": "A", "role": "ML Intern", "start": "2024-05", "end": "2025-07"}]}
    assert map_field(f("Total experience (years)"), "experience.total_years", worked)["value"] == "1"


def test_education_summary_box():
    field = f("Education or relevant training", "textarea")
    assert classify(field) == "education.summary"
    a = map_field(field, "education.summary", PROFILE)
    assert a["status"] == "review" and "B.Tech" in a["value"] and "Class 12" in a["value"] and "Certifications" in a["value"]
