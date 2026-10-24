"""Drafter agent: writes answers to free-text questions.

Phase 3 version: TEMPLATES filled only with profile facts and the Matcher's
picks (no LLM yet; Phase 8/9 replaces `write_draft` with our fine-tuned model
via Ollama). It recognises:
  - motivation ("Why would you like to join X?", "Why are you interested...")
  - project ("Tell us about your best project", "Describe a project...")
Anything else gets no draft and stays "write it yourself".

Only the non-sensitive slice of the profile is used (services/profile_facts.py).
Tests swap `write_draft` out to simulate other drafts.
"""

import re
from datetime import date

from app import config
from services.profile_facts import safe_profile

MOTIVATION = re.compile(r"\bwhy\b.*\b(join|work|interested|apply|applying|want|like)\b|\b(interest|motivat)\w*\b.*\b(role|position|company|team|us)\b"
                        r"|\bwhat (excites|attracts|interests) you\b", re.I)
PROJECT = re.compile(r"\b(project|something you (built|made)|work you are proud|proud of)\b", re.I)


def company_from(label: str, job_text: str) -> str | None:
    """'Why would you like to join RingTrunk?' -> 'RingTrunk'."""
    m = re.search(r"\b(?:join|at|with|for)\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})", label)
    if m and m.group(1).lower() not in {"us", "our", "the", "this"}:
        return m.group(1).rstrip("?.!,")
    return None


def _first_sentence(text: str) -> str:
    text = (text or "").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return (m.group(1) if m else text).strip()


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


def _student_line(facts: dict) -> str:
    d = facts["degree"]
    if not d.get("name"):
        return ""
    field = d.get("branch") or ""
    if d.get("specialization"):
        field = f"{field} ({d['specialization']})" if field else d["specialization"]
    at = f" at {d['college']}" if d.get("college") else ""
    year = d.get("graduation_year")
    try:
        status = "graduating in" if int(year) >= date.today().year else "graduated in"
    except (TypeError, ValueError):
        status, year = "", ""
    tail = f", {status} {year}" if year else ""
    return f"I'm a {d['name']} {field} student{at}{tail}.".replace("  ", " ")


def _best_project(facts: dict, fit: dict | None) -> dict | None:
    projects = facts["projects"]
    if not projects:
        return None
    if fit and fit.get("best_projects"):
        return projects[fit["best_projects"][0]["index"]]
    return projects[0]


def _fit_to_length(sentences: list[str], limit: int | None) -> str:
    text = " ".join(s for s in sentences if s)
    if not limit:
        return text
    while len(text) > limit and len(sentences) > 1:
        sentences = sentences[:-1]
        text = " ".join(s for s in sentences if s)
    return text if len(text) <= limit else ""


# ---------- LLM drafting (Phase 9) ----------

DRAFT_SYSTEM = """You write short answers to job application questions for a student, in the first person.
Use ONLY the facts given. Never invent skills, tools, companies, numbers, grades, awards, roles or experiences.
Be specific and plain: name the actual project or skill from the facts. No clichés, no greetings, no sign-off.
Describe a project or activity only with what its facts say: do not add features, data, users, events, results or roles.
Saying you don't have something yet (and what you do have instead) is better than stretching a fact.
If the facts contain nothing relevant to the question, reply with exactly: NO_DRAFT"""


def facts_text(facts: dict, fit: dict) -> str:
    """The non-sensitive profile (and the Matcher's picks) as plain lines for the model."""
    lines = [_student_line(facts)]
    skills = sorted({s for group in facts["skills"].values() for s in group})
    if skills:
        lines.append("Skills: " + ", ".join(skills))
    for p in facts["projects"]:
        lines.append(f"Project: {p.get('title')}: {p.get('summary', '')} (tech: {', '.join(p.get('tech') or [])})")
    for e in facts["experience"]:
        lines.append(f"Experience: {e.get('role')} at {e.get('company')} ({e.get('start')} to {e.get('end') or 'present'}): {e.get('summary', '')}")
    if not facts["experience"]:
        lines.append("Experience: none yet (no internships or jobs).")
    if facts["certifications"]:
        lines.append("Certifications: " + "; ".join(c.get("name", "") for c in facts["certifications"]))
    if facts["achievements"]:
        lines.append("Achievements: " + "; ".join(facts["achievements"]))
    if facts["languages_spoken"]:
        lines.append("Languages: " + ", ".join(facts["languages_spoken"]))
    if fit.get("best_projects"):
        lines.append("Most relevant projects for this job: " + ", ".join(b["title"] for b in fit["best_projects"]))
    if fit.get("matched_skills"):
        lines.append("Skills that match this job: " + ", ".join(fit["matched_skills"]))
    return "\n".join(line for line in lines if line)


def length_rule(field: dict, retry: int) -> str:
    """What the box allows: "max 100 words", "3-4 sentences", max characters, or a sensible default."""
    hint = " ".join(field.get(k) or "" for k in ("label", "placeholder", "helper_text"))
    words_limit = re.search(r"(\d+)\s*words?", hint, re.I)
    sentences = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(sentences|lines)", hint, re.I)
    if words_limit:
        rule = f"at most {words_limit.group(1)} words"
    elif sentences:
        rule = f"{sentences.group(1)}-{sentences.group(2)} {sentences.group(3)}"
    else:
        rule = "60-110 words"
    if field.get("max_length"):
        chars = int(field["max_length"] * (0.8 if retry else 0.95))
        rule += f", and under {chars} characters"
    return rule


def llm_draft(field: dict, state: dict) -> dict:
    """A draft from the local model. On a retry, the Verifier's reasons go back into the prompt."""
    from services import ollama_client
    facts = safe_profile(state.get("profile") or {})
    fit = state.get("fit") or {}
    retry = (state.get("retries") or {}).get(field["id"], 0)
    jd = (state.get("job_description") or "").strip()
    company = company_from(field.get("label", ""), jd)
    parts = ["FACTS:", facts_text(facts, fit), ""]
    if jd:
        parts += ["JOB DESCRIPTION (for relevance; never claim its requirements as your own unless the facts say so):", jd[:1500], ""]
    if company:
        parts.append(f"Company: {company}")
    parts += [f"QUESTION: {field.get('label', '')}"]
    if field.get("helper_text"):
        parts.append(f"Hint: {field['helper_text'][:200]}")
    parts.append(f"LENGTH: {length_rule(field, retry)}.")
    previous = (state.get("verification") or {}).get(field["id"])
    if retry and previous and not previous["passed"]:
        old = ((state.get("drafts") or {}).get(field["id"]) or {}).get("text", "")
        parts += ["", f"Your previous answer was rejected: {'; '.join(previous['reasons'])}.",
                  f"Previous answer: {old}", "Write a corrected answer that fixes this."]
    text, seconds = ollama_client.chat(DRAFT_SYSTEM, "\n".join(parts), temperature=0.3)
    text = re.sub(r"^\s*(answer|response)\s*:\s*", "", text.strip(), flags=re.I).strip().strip('"').strip()
    if not text or "NO_DRAFT" in text:
        return {"text": "", "kind": "none", "seconds": round(seconds, 1)}
    return {"text": text, "kind": "llm", "seconds": round(seconds, 1)}


# A "question" that says nothing ("Your answer", "Type here", one or two words): never drafted.
# If the extension misread the page, writing anyway produced a generic essay in the wrong box.
VAGUE = re.compile(r"^\W*(your (answer|response)|type (your answer|here|something)|enter (your answer|here|text)|"
                   r"answer( here)?|short answer( text)?|long answer( text)?|write (here|your answer)|response)\W*$", re.I)


def is_vague_question(label: str) -> bool:
    return bool(VAGUE.match(label or "")) or len(re.findall(r"[A-Za-z]+", label or "")) < 3


def write_draft(field: dict, state: dict) -> dict:
    """Returns {"text": str, "kind": str}. Empty text means "no draft"."""
    label = field.get("label", "")
    if is_vague_question(label):
        return {"text": "", "kind": "none"}
    if re.search(r"\b(record|video|upload|share the link|drive link|onedrive)\b", label, re.I):
        return {"text": "", "kind": "none"}  # they want a link to something you made, not text
    from services import ollama_client
    if ollama_client.use_llm(state):
        try:
            return llm_draft(field, state)
        except (OSError, ValueError, KeyError):
            pass  # Ollama busy, slow or broken: fall back to the template draft
    return template_draft(field, state)


def template_draft(field: dict, state: dict) -> dict:
    """The no-LLM version: fills templates with profile facts and the Matcher's picks."""
    facts = safe_profile(state.get("profile") or {})
    fit = state.get("fit") or {}
    label = field.get("label", "")
    project = _best_project(facts, fit)
    skills = (fit.get("matched_skills") or [])[:3]
    # A retry after the Verifier said "too long" gets a tighter limit.
    limit = field.get("max_length")
    if limit and (state.get("retries") or {}).get(field["id"]):
        limit = int(limit * 0.8)

    if re.search(r"\b(record|video|upload|share the link|drive link|onedrive)\b", label, re.I):
        return {"text": "", "kind": "none"}  # they want a link to something you made, not text

    if MOTIVATION.search(label):
        company = company_from(label, state.get("job_description") or "") or "your team"
        sentences = [_student_line(facts)]
        if project:
            sentences.append(f"In my project {project['title']}, I {_lower_first(_first_sentence(project.get('summary', '')))}"
                             if project.get("summary") else f"One project I'm proud of is {project['title']}.")
        if skills:
            sentences.append(f"I'd like to join {company} to keep working with {', '.join(skills)} on real problems.")
        else:
            sentences.append(f"I'd like to join {company} to apply these skills to real problems and keep learning.")
        return {"text": _fit_to_length(sentences, limit), "kind": "motivation"}

    if PROJECT.search(label) and project:
        tech = ", ".join(project.get("tech") or [])
        sentences = [f"{project['title']}: {project.get('summary', '').strip()}".strip()]
        if tech:
            sentences.append(f"Tech used: {tech}.")
        if project.get("link"):
            sentences.append(f"Link: {project['link']}")
        return {"text": _fit_to_length(sentences, limit), "kind": "project"}

    return {"text": "", "kind": "none"}


def drafter(state: dict) -> dict:
    by_id = {f["id"]: f for f in state["fields"]}
    drafts = dict(state.get("drafts") or {})
    retries = dict(state.get("retries") or {})
    verification = state.get("verification") or {}

    for field_id in state["free_text_fields"]:
        previous = verification.get(field_id)
        if previous is None:
            drafts[field_id] = write_draft(by_id[field_id], {**state, "retries": retries})  # first attempt
        elif not previous["passed"] and retries.get(field_id, 0) < config.MAX_DRAFT_RETRIES:
            retries[field_id] = retries.get(field_id, 0) + 1  # rejected: try again
            drafts[field_id] = write_draft(by_id[field_id], {**state, "retries": retries})

    return {"drafts": drafts, "retries": retries, "trace": ["drafter"]}
