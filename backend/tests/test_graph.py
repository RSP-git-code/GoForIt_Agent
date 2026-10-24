"""Routing and fallback tests for the agent graph (CLAUDE.md §4.3)."""

import pytest

from agents import drafter, verifier
from agents.graph import run_fill
from services import ollama_client

PROFILE = {"personal": {"full_name": "Ananya Rao", "email": "a@example.com"}}
STANDARD = [{"id": "f1", "label": "Full name", "kind": "text", "options": []},
            {"id": "f2", "label": "Email", "kind": "email", "options": []}]
QUESTION = {"id": "q1", "label": "Why do you want to join Acme?", "kind": "textarea", "options": []}


def action(result, field_id):
    return next(a for a in result["actions"] if a["field_id"] == field_id)


def test_no_free_text_skips_draft_branch():
    r = run_fill(STANDARD, PROFILE)
    assert r["trace"] == ["page_analyzer", "mapper", "assemble"]
    assert [a["status"] for a in r["actions"]] == ["filled", "filled"]


def test_free_text_goes_down_draft_branch():
    r = run_fill(STANDARD + [QUESTION], PROFILE)
    assert r["trace"] == ["page_analyzer", "mapper", "matcher", "drafter", "verifier", "assemble"]
    q = action(r, "q1")
    # The template Drafter writes from the profile; drafts are always yellow for review.
    assert q["status"] == "review" and q["source"] == "draft" and "Acme" in q["value"]


def test_llm_offline_skips_drafting_with_warning(monkeypatch):
    monkeypatch.setattr(ollama_client, "is_available", lambda: False)
    r = run_fill(STANDARD + [QUESTION], PROFILE)
    assert "drafter" not in r["trace"] and "llm_offline" in r["trace"]
    assert any("offline" in w for w in r["warnings"])
    assert action(r, "f1")["status"] == "filled"  # standard fields still fill


def test_verified_draft_is_returned_for_review(monkeypatch):
    monkeypatch.setattr(drafter, "write_draft", lambda field, state: {"text": "Because of X."})
    r = run_fill([QUESTION], PROFILE)
    q = action(r, "q1")
    assert (q["status"], q["value"], q["source"]) == ("review", "Because of X.", "draft")
    assert r["trace"].count("drafter") == 1


def test_rejected_draft_retries_twice_then_flags_red(monkeypatch):
    calls = []
    monkeypatch.setattr(drafter, "write_draft", lambda field, state: calls.append(1) or {"text": "I led a team at Google."})
    monkeypatch.setattr(verifier, "check_draft", lambda d, field, state: {"passed": False, "reasons": ["invented company: Google"]})
    r = run_fill([QUESTION], PROFILE)
    assert len(calls) == 3  # first draft + 2 retries
    assert r["trace"].count("drafter") == 3 and r["trace"][-1] == "assemble"
    q = action(r, "q1")
    assert q["status"] == "missing" and q["value"] is None
    assert "invented company" in q["reason"]


def test_draft_accepted_on_retry(monkeypatch):
    attempts = iter(["I worked at Google.", "I built a RAG resume scanner."])
    monkeypatch.setattr(drafter, "write_draft", lambda field, state: {"text": next(attempts)})
    monkeypatch.setattr(verifier, "check_draft",
                        lambda d, field, state: {"passed": "Google" not in d["text"], "reasons": ["invented company"]})
    r = run_fill([QUESTION], PROFILE)
    q = action(r, "q1")
    assert q["status"] == "review" and q["value"] == "I built a RAG resume scanner."
    assert r["trace"].count("drafter") == 2
