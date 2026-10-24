"""Verifier agent: checks each draft only uses facts from the profile.

Rule checks (Phase 3):
  - fits the box: no longer than the field's max length
  - every number in the draft appears in the profile (no invented CGPA,
    percentages, years or counts)
  - every technology term in the draft appears in the profile (no invented skills)
Phase 9 adds an LLM-as-judge on top. Tests swap `check_draft` out to simulate rejections.
"""

import re

from agents.matcher import TECH_TERMS
from app import config
from services.option_match import words
from services.profile_facts import corpus, numbers_in, safe_profile


def check_draft(draft: dict, field: dict, state: dict) -> dict:
    """Returns {"passed": bool, "reasons": [str]}."""
    text = draft.get("text") or ""
    if not text:
        return {"passed": True, "reasons": []}  # nothing to check: field stays "write it yourself"

    facts = safe_profile(state.get("profile") or {})
    known = corpus(facts)
    reasons = []

    limit = field.get("max_length")
    if limit and len(text) > limit:
        reasons.append(f"too long ({len(text)} > {limit} characters)")

    invented_numbers = sorted(n for n in numbers_in(text) if f" {n} " not in known and n not in known)
    if invented_numbers:
        reasons.append(f"numbers not in your profile: {', '.join(invented_numbers)}")

    # Sentences saying you DON'T have something ("I haven't used Kubernetes yet") claim nothing.
    claims_text = " ".join(s for s in sentences(text) if not NEGATION.search(words(s)))
    drafted = f" {words(claims_text)} "
    # Concrete tools only: "machine learning" or "LLM" are fields a student can talk about,
    # "Kubernetes" or "AWS" are skills they'd be claiming.
    invented_tech = [t for t in TECH_TERMS if t not in DOMAINS and f" {words(t)} " in drafted and f" {words(t)} " not in known]
    if invented_tech:
        reasons.append(f"skills not in your profile: {', '.join(invented_tech)}")

    if not reasons and draft.get("kind") == "llm":
        # What the question itself names (the company in "Why join Acme AI?") is known too.
        # The question and job description name the company and what it does ("Why join Acme AI?",
        # "...builds LLM hiring tools"): saying those back is not a claim about you. (Tools you claim
        # to use are still checked against your profile by the skills check above.)
        context = f"{known} {words(field.get('label') or '')} {words(state.get('job_description') or '')} "
        reasons += judge_claims(claims_text, facts, state, context)
    return {"passed": not reasons, "reasons": reasons}


NEGATION = re.compile(r"\b(never|not|no|havent|hasnt|dont|didnt|cannot|cant|yet to|without)\b")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


JUDGE_SYSTEM = """You check a student's job-application answer against their profile facts.
List every claim in the ANSWER that the FACTS do not support: skills, tools, projects, companies, roles,
numbers, awards, experiences or results that are not in the facts. Opinions, interests and plans
("I want to learn", "I'm excited about") are fine. Rewording a fact is fine. Return an empty list if every claim is supported."""
JUDGE_SCHEMA = {"type": "object", "properties": {"unsupported": {"type": "array", "items": {"type": "string"}}},
                "required": ["unsupported"]}


# Broad fields (not tools you'd claim to know): never counted as invented skills.
DOMAINS = {"machine learning", "deep learning", "reinforcement learning", "computer vision", "nlp", "llm", "llms",
           "generative ai", "data analysis", "data science", "statistics", "recommendation", "classification",
           "time series", "apis", "rest api", "mlops", "devops"}
# Words that turn a sentence into a checkable claim about you.
CLAIM_WORDS = {"won", "win", "winner", "winning", "prize", "award", "awarded", "first", "1st", "second", "third", "topped",
               "led", "lead", "leading", "managed", "manager", "managing", "mentored", "head", "headed", "founded", "founder",
               "intern", "internship", "interned", "employed", "employer", "worked", "client", "clients", "customers",
               "certified", "certification", "certificate", "deployed", "production", "scale", "years", "year", "published",
               "patent", "fluent", "native", "rank", "ranked", "selected", "scholarship"}


def checkable(claim: str, known: str) -> bool:
    """Keep a judge's claim only if it names something risky the profile doesn't have: a name,
    a number or a claim word (won, led, intern, certified, years...). Opinions and rewordings pass."""
    tokens = re.findall(r"[A-Za-z][\w+#.-]*|\d+(?:\.\d+)?", claim)
    for i, tok in enumerate(tokens):
        w = words(tok)
        if not w or f" {w} " in known:
            continue
        if tok[0].isdigit() or w in CLAIM_WORDS or (tok[0].isupper() and i > 0 and tok not in ("I", "I'm")):
            return True
    return False


def judge_claims(text: str, facts: dict, state: dict, context: str | None = None) -> list[str]:
    """LLM-as-judge: claims the local model finds unsupported. [] if fine, or if the model can't be reached.
    Small local models flag almost anything, so each claim must also pass checkable()."""
    import json
    from agents.drafter import facts_text
    from services import ollama_client
    try:
        reply, _ = ollama_client.chat(JUDGE_SYSTEM, f"FACTS:\n{facts_text(facts, state.get('fit') or {})}\n\nANSWER:\n{text}",
                                      schema=JUDGE_SCHEMA, temperature=0, model=config.JUDGE_MODEL)
        claims = [str(c).strip() for c in json.loads(reply).get("unsupported") or [] if len(str(c).strip()) > 3]
    except (OSError, ValueError, KeyError):
        return []  # the rule checks above already ran; the panel still marks it as an AI draft to review
    known = context or corpus(facts)
    claims = [c for c in claims if checkable(c, known) and not NEGATION.search(words(c))]
    return [f"not in your profile: {c}" for c in claims[:3]]


def verifier(state: dict) -> dict:
    by_id = {f["id"]: f for f in state["fields"]}
    verification = dict(state.get("verification") or {})
    for field_id, draft in (state.get("drafts") or {}).items():
        old = verification.get(field_id)
        if old and old["passed"]:
            continue  # already accepted on an earlier round
        verification[field_id] = check_draft(draft, by_id[field_id], state)
    return {"verification": verification, "trace": ["verifier"]}
