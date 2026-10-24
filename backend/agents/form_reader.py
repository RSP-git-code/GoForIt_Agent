"""Form Reader agent: the local LLM reads the form like a person and answers from the profile.

The rules (Page Analyzer + Mapper) fill the obvious fields instantly. The Form
Reader gets the rest: questions the rules couldn't place or flagged, and ones
that need context ("Profile link" right after "Coding platform: LeetCode",
"Foreign language" = not English/Hindi, "Branch (branch and specialization)").

It sees the whole page (every question, its options, its section, its
neighbours) plus the profile as plain facts, and must cite, for every answer,
the fact it used. answer=null when the profile doesn't say: it must never
invent (CLAUDE.md rule 6). ground() then checks each answer against the cited
fact before anything reaches the page.

Privacy: phone, emails, address, pincode, date of birth, category and
registration number are never given to the model (the rules fill those). The
model runs in Ollama on this laptop (127.0.0.1); nothing leaves it.
"""

import json
import re
import time
import urllib.request
from datetime import date

from services.option_match import match_option, words

# Never shown to the model (CLAUDE.md §6: not passed to the AI agents).
HIDDEN = re.compile(r"^personal\.(email|college_email|phone|alternate_phone|date_of_birth|category|"
                    r"permanent_address|pincode)$|registration_number|^resume_file|^relatives|^diversity")


def profile_facts(profile: dict) -> dict[str, str]:
    """The profile as flat facts: {"education.degree.cgpa": "8.03", "links.leetcode": "https://...", ...}."""
    facts = {}

    def walk(value, path):
        if HIDDEN.search(path):
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(value, list):
            if value and all(isinstance(x, dict) for x in value):  # projects, experience, certifications
                for i, item in enumerate(value, 1):
                    walk(item, f"{path}[{i}]")
            elif value:
                facts[path] = "; ".join(str(x) for x in value)
        elif value not in (None, ""):
            facts[path] = str(value)

    walk(profile or {}, "")
    if not (profile or {}).get("experience"):
        facts["experience"] = "none (no internships or jobs; 0 years of work experience)"
    return facts


def fact_key(cited, facts: dict[str, str]) -> str | None:
    """Models sometimes cite "key: value" or "key=value" instead of just the key."""
    if not cited:
        return None
    cited = str(cited).strip()
    if cited in facts:
        return cited
    head = re.split(r"\s*[:=]\s*", cited, maxsplit=1)[0].strip()
    return head if head in facts else None


SYSTEM = """You fill job application forms for a student, using ONLY the facts given.
For each question, give the answer the student would type or pick, and the fact key it comes from.
Rules:
- Use only the facts. If the facts don't answer it, answer null. Never guess or invent.
- For questions with options, answer with one option exactly as written (or several, comma-separated, for "select all").
- Yes/No questions: answer "Yes" or "No" only when a fact clearly settles it, else null.
- Use context: the section a question is in and the questions before it.
- One-line boxes get a short answer, not a list of everything.
- Do not answer: how you heard about the job, references, pronouns, anything the facts don't cover."""


def build_prompt(fields: list[dict], facts: dict[str, str], today: date) -> str:
    lines = [f"Today is {today:%d %B %Y}.", "", "FACTS (key: value):"]
    lines += [f"- {k}: {v}" for k, v in facts.items()]
    lines += ["", "FORM QUESTIONS (in page order):"]
    for f in fields:
        desc = f'- id={f["id"]} | question: {f.get("label") or f.get("aria_label") or f.get("placeholder")}'
        if f.get("section"):
            desc += f' | section: {f["section"]}'
        if f.get("placeholder"):
            desc += f' | placeholder: {f["placeholder"]}'
        if f.get("helper_text"):
            desc += f' | hint: {f["helper_text"][:150]}'
        desc += f' | type: {f.get("kind") or "text"}'
        if f.get("options"):
            desc += " | options: " + " / ".join(f["options"][:25])
        lines.append(desc)
    lines += ["", 'Reply as JSON: {"answers": [{"id": "...", "answer": "..." or null, "fact": "fact key used" or null}]}']
    return "\n".join(lines)


SCHEMA = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "answer": {"type": ["string", "null"]}, "fact": {"type": ["string", "null"]}},
        "required": ["id", "answer", "fact"]}}},
    "required": ["answers"],
}


def ask_ollama(model: str, prompt: str, url: str = "http://127.0.0.1:11434", timeout: float = 300) -> tuple[dict, float]:
    """One chat request to the local Ollama server. Returns (parsed JSON, seconds)."""
    body = {"model": model, "stream": False, "format": SCHEMA, "keep_alive": "30m",
            "options": {"temperature": 0, "num_ctx": 6144},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
    if model.startswith("qwen3"):
        body["think"] = False  # Qwen3 "thinks" out loud by default: slow, and not needed here
    req = urllib.request.Request(f"{url}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        reply = json.load(resp)
    content = reply["message"]["content"]
    try:
        return json.loads(content), time.time() - start
    except ValueError:
        return {"answers": []}, time.time() - start


def _numbers(text: str) -> set[str]:
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))}


def ground(field: dict, answer: str | None, cited: str | None, facts: dict[str, str]) -> tuple[bool, str]:
    """Is the answer supported by the cited fact? (The Verifier's rule check for Form Reader answers.)"""
    if answer is None or str(answer).strip() == "":
        return True, "left for you"
    answer = str(answer).strip()
    options = field.get("options") or []
    if options:
        picked = [a.strip() for a in answer.split(",")] if field.get("kind") == "checkbox" else [answer]
        if not all(match_option(a, options) for a in picked):
            return False, f'"{answer}" is not one of the options'
    key = fact_key(cited, facts)
    if not key:
        return False, "no profile fact cited"
    value = facts[key]
    if options or words(answer) in ("yes", "no"):
        # A real option (its wording/numbers come from the page) backed by a real fact.
        return True, f"from {key}"
    # Numbers must come from the fact (CGPA x 10 = percentage is the one conversion allowed).
    allowed = _numbers(value) | {str(round(float(n) * 10, 2)).rstrip("0").rstrip(".") for n in _numbers(value) if float(n) <= 10}
    if not _numbers(answer) <= allowed:
        return False, f"numbers not in {key}"
    # Most of the answer's words must appear in the fact (or in the chosen option).
    support = f" {words(value)} {words(' '.join(options))} "
    content = [w for w in words(answer).split() if len(w) > 2]
    if content and sum(f" {w} " in support for w in content) / len(content) < 0.6:
        return False, f"not supported by {key}"
    return True, f"from {key}"


def read_form(fields: list[dict], profile: dict, model: str, today: date | None = None) -> tuple[dict, float]:
    """{field_id: {"answer", "fact", "ok", "reason"}} for every field, plus seconds taken."""
    facts = profile_facts(profile)
    reply, seconds = ask_ollama(model, build_prompt(fields, facts, today or date.today()))
    by_id = {f["id"]: f for f in fields}
    out = {}
    for a in reply.get("answers") or []:
        if a.get("id") in by_id:
            ok, reason = ground(by_id[a["id"]], a.get("answer"), a.get("fact"), facts)
            out[a["id"]] = {"answer": a.get("answer"), "fact": a.get("fact"), "ok": ok, "reason": reason}
    return out, seconds
