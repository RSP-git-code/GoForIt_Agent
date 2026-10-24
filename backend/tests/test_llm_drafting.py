"""Phase 9 loop with a fake local model: Drafter -> Verifier (rules + LLM judge) -> retry with the reasons."""

import json

import pytest

from agents.graph import run_fill
from services import ollama_client

PROFILE = {
    "education": {"degree": {"name": "B.Tech", "branch": "CSE", "college": "Example Institute", "graduation_year": "2027"}},
    "skills": {"languages": ["Python"], "ml_ai": ["PyTorch", "LangChain"]},
    "projects": [{"title": "Resume Matcher", "summary": "RAG app that matches resumes to jobs.", "tech": ["Python", "LangChain"]}],
    "experience": [],
}
WHY = {"id": "w", "label": "Why do you want to join Acme?", "kind": "textarea", "options": [], "placeholder": "", "helper_text": ""}


@pytest.fixture
def fake_model(monkeypatch):
    """Replaces the Ollama call. `replies` is a list of functions(system, user) -> reply, used in order."""
    calls = []

    def use(replies):
        monkeypatch.setattr(ollama_client, "use_llm", lambda state=None: True)
        monkeypatch.setattr(ollama_client, "is_available", lambda: True)

        def chat(system, user, model=None, schema=None, temperature=0.2, timeout=None):
            calls.append({"system": system, "user": user, "schema": schema})
            reply = replies[min(len(calls) - 1, len(replies) - 1)]
            return reply(system, user), 0.1
        monkeypatch.setattr(ollama_client, "chat", chat)
        return calls
    return use


def judge_ok(system, user):
    return json.dumps({"unsupported": []})


def action(result, field_id="w"):
    return next(a for a in result["actions"] if a["field_id"] == field_id)


def test_rejected_draft_is_rewritten_with_the_verifiers_reasons(fake_model):
    calls = fake_model([
        lambda s, u: "I built Resume Matcher with Python and Kubernetes.",   # draft 1: invents Kubernetes
        lambda s, u: "I built Resume Matcher, a RAG app in Python and LangChain, and want to do similar work at Acme.",
        judge_ok,                                                            # judge accepts draft 2
    ])
    result = run_fill([WHY], PROFILE, "We use Python and LangChain.")
    a = action(result)
    assert "Kubernetes" not in a["value"] and "Resume Matcher" in a["value"]
    assert a["status"] == "review" and "draft" in a["reason"].lower()
    retry_prompt = calls[1]["user"]
    assert "rejected" in retry_prompt and "kubernetes" in retry_prompt.lower()  # the reason went back to the Drafter
    assert result["trace"].count("drafter") == 2


def test_judge_catches_claims_the_rules_cannot(fake_model):
    fake_model([
        lambda s, u: "I led a team of five at a hackathon and won first prize with Resume Matcher.",
        lambda s, u: json.dumps({"unsupported": ["won first prize at a hackathon", "led a team of five"]}),
    ])
    a = action(run_fill([WHY], PROFILE, None))
    # Rejected every time (same invented claim) -> after 2 retries the field is left for you, with the reason.
    assert not a.get("value")
    assert "not in your profile" in a["reason"]


def test_no_draft_when_the_profile_has_nothing_relevant(fake_model):
    fake_model([lambda s, u: "NO_DRAFT"])
    q = {**WHY, "id": "m", "label": "Describe your experience managing direct reports."}
    a = action(run_fill([q], PROFILE, None), "m")
    assert not a.get("value")


def test_ollama_failure_falls_back_to_the_template(monkeypatch):
    monkeypatch.setattr(ollama_client, "use_llm", lambda state=None: True)
    monkeypatch.setattr(ollama_client, "is_available", lambda: True)

    def broken(*args, **kwargs):
        raise OSError("connection refused")
    monkeypatch.setattr(ollama_client, "chat", broken)
    a = action(run_fill([WHY], PROFILE, None))
    assert "Resume Matcher" in (a.get("value") or "")  # the template still drafts from the profile


def test_private_details_are_not_in_the_drafting_prompt(fake_model):
    calls = fake_model([lambda s, u: "I built Resume Matcher.", judge_ok])
    profile = {**PROFILE, "personal": {"email": "asha@example.com", "phone": "+91 9876543210", "date_of_birth": "2004-01-15"}}
    run_fill([WHY], profile, None)
    prompts = " ".join(c["user"] for c in calls)
    for secret in ("asha@example.com", "9876543210", "2004-01-15"):
        assert secret not in prompts


def test_judge_claims_must_name_something_checkable():
    from agents.verifier import checkable
    from services.profile_facts import corpus, safe_profile
    known = corpus(safe_profile(PROFILE))
    assert checkable("internship at Infosys", known)
    assert checkable("won first prize", known)
    assert checkable("3 years of experience", known)
    assert not checkable("I am proud of the Resume Matcher project", known)   # a fact, reworded
    assert not checkable("I want to grow as an engineer", known)              # an opinion


def test_broad_fields_are_not_invented_skills():
    from agents.verifier import check_draft
    field = {"id": "x", "label": "Why us?", "kind": "textarea"}
    ok = check_draft({"text": "I want to work on machine learning and LLM products.", "kind": "template"}, field, {"profile": PROFILE})
    assert ok["passed"]
    bad = check_draft({"text": "I deployed it on Kubernetes.", "kind": "template"}, field, {"profile": PROFILE})
    assert not bad["passed"]


def test_honest_negations_and_the_company_in_the_question_pass(fake_model):
    fake_model([
        lambda s, u: "I haven't managed direct reports yet. I co-built Resume Matcher with Python and LangChain.",
        lambda s, u: json.dumps({"unsupported": ["I have never managed direct reports"]}),
    ])
    q = {**WHY, "id": "m", "label": "Describe your experience managing direct reports."}
    assert action(run_fill([q], PROFILE, None), "m")["value"].startswith("I haven't managed")
    fake_model([
        lambda s, u: "I want to join Acme AI to build LangChain apps like Resume Matcher.",
        lambda s, u: json.dumps({"unsupported": ["I want to join Acme AI"]}),
    ])
    assert "Acme AI" in action(run_fill([WHY], PROFILE, None))["value"]


def test_empty_strengths_answer_goes_to_the_drafter(fake_model):
    calls = fake_model([lambda s, u: "I learn new tools quickly: I picked up LangChain for Resume Matcher.", judge_ok])
    q = {**WHY, "id": "s", "label": "What are your key strengths?"}
    a = action(run_fill([q], PROFILE, None), "s")
    assert "LangChain" in a["value"] and calls and calls[-1]["user"]


def test_fill_reports_which_questions_could_get_an_ai_draft():
    name = {"id": "n", "label": "Full Name", "kind": "text", "options": [], "placeholder": "", "helper_text": ""}
    strengths = {**WHY, "id": "s", "label": "What are your strengths?"}
    result = run_fill([name, WHY, strengths], PROFILE, None)
    assert set(result["draftable"]) == {"w", "s"}


def test_draft_endpoint_runs_the_loop_for_one_question(fake_model, monkeypatch, caplog):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(ollama_client, "ollama_running", lambda timeout=0.5: True)
    fake_model([lambda s, u: "I built Resume Matcher with Python and LangChain.", judge_ok])
    with caplog.at_level("INFO"):
        resp = TestClient(app).post("/draft", json={"field": WHY, "profile": PROFILE, "job_description": None})
    body = resp.json()
    assert resp.status_code == 200 and body["action"]["value"].startswith("I built Resume Matcher")
    assert "check every sentence" in body["action"]["reason"]
    assert "drafter" in body["trace"] and "verifier" in body["trace"]
    assert "Resume Matcher" not in caplog.text  # the answer is never logged


def test_draft_endpoint_when_ollama_is_off(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(ollama_client, "ollama_running", lambda timeout=0.5: False)
    body = TestClient(app).post("/draft", json={"field": WHY, "profile": PROFILE}).json()
    assert body["action"]["value"] is None and "isn't running" in body["action"]["reason"]


def test_vague_or_filler_questions_are_never_drafted(fake_model):
    calls = fake_model([lambda s, u: "I am applying for the AI Software Engineer position..."])
    for label in ("Your answer", "Type here", "Answer"):
        q = {**WHY, "id": "v", "label": label}
        result = run_fill([q], PROFILE, None)
        assert not action(result, "v").get("value") and "v" not in result["draftable"], label
    assert not calls  # the model was never even asked
