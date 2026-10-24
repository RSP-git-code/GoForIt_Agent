"""Agent Octo, as a chat: the side panel sends each message here (POST /octo).

Most replies are deterministic (instant, nothing invented):
  - a pasted job description   -> the Coach's analysis (agents/coach.py), as a few chat messages
  - "how do I learn Docker?"   -> that skill's effort, curated free resources and a "show it" tip
  - "which project should I mention?" -> the project that matches most of this job's skills
  - "make me a plan"           -> a week-by-week plan from the missing skills and their effort
Anything else goes to the local LLM (Ollama) as Octo, told only this job's analysis and the
non-sensitive profile; any link it writes is removed (links only come from the curated list).
"""

import re

from agents import octo_plan
from agents.coach import coach
from services import ollama_client
from services.learning_resources import SKILLS, videos_and_courses
from services.option_match import words
from services.profile_facts import safe_profile

JD_HINT = re.compile(r"\b(requirements?|responsibilities|qualifications?|what you.ll do|about the role|skills|experience|"
                     r"eligibility|job description|we are looking for)\b", re.I)


def looks_like_job_description(text: str) -> bool:
    return len(text) > 350 or (text.count("\n") >= 3 and bool(JD_HINT.search(text)))


def _skill_in(text: str) -> str | None:
    t = f" {words(text)} "
    for name, info in SKILLS.items():
        if any(f" {words(a)} " in t for a in [name] + info["aliases"]):
            return name
    return None


def _skills_in(text: str) -> list[str]:
    """Every curated skill named in the text, in the order they appear."""
    t = f" {words(text)} "
    found = []
    for name, info in SKILLS.items():
        spots = [t.find(f" {words(a)} ") for a in [name] + info["aliases"] if f" {words(a)} " in t]
        if spots:
            found.append((min(spots), name))
    return [name for _, name in sorted(found)]


def _llm_topics(text: str) -> list[str]:
    """Learnable topics in a free-form Octo reply (e.g. "CUDA", "computer architecture"), via the
    local LLM. Only topics written in the text itself are kept, so nothing new is invented."""
    if not text or not ollama_client.ollama_running():
        return []
    try:
        out, _ = ollama_client.chat("You extract topics. Reply with only names, comma-separated, nothing else.",
                                    "List the 1-3 main skills or topics a student should learn, from this text:\n" + text,
                                    temperature=0)
    except (OSError, ValueError, KeyError):
        return []
    have = f" {words(text)} "
    topics = []
    for t in re.split(r"[,\n;]", out):
        t = t.strip(" .-*\"'")
        if 1 < len(t) <= 40 and f" {words(t)} " in have and t.lower() not in [x.lower() for x in topics]:
            topics.append(t)
    return topics[:3]


def context_topics(history: list[dict], result: dict | None) -> list[str]:
    """What "that" / "resources" refers to: topics from Octo's last reply, else this job's gaps."""
    last = next((h.get("text", "") for h in reversed(history) if h.get("role") == "octo"), "")
    topics = _skills_in(last)[:3] or _llm_topics(last)
    if not topics:
        topics = [m["skill"] for m in (result or {}).get("missing_required", [])[:3]]
    return topics


def topic_links(topic: str) -> list[dict]:
    """Links for any topic: curated ones for known skills, free searches for the rest."""
    if topic in SKILLS:
        return _links(topic)
    return [{"title": t, "url": u} for t, u in videos_and_courses(topic)]


def _links(skill: str) -> list[dict]:
    """Free videos / courses first, then the official docs (opened by the student in a new tab)."""
    info = SKILLS[skill]
    return [{"title": t, "url": u} for t, u in videos_and_courses(skill) + list(info["resources"][:1])]


def _chips(result: dict | None, after: str = "") -> list[str]:
    if not result:
        return ["Which jobs should I apply to today?", "How do I learn Docker?", "What can you do?"]
    if after == "plan":
        return ["Add this plan to my calendar", "Show me tutorials", "Check another job"]
    chips = [f"How do I learn {m['skill']}?" for m in result["missing_required"][:2]]
    if result["matched"]:
        chips.append("Which project should I mention?")
    if result["missing_required"]:
        chips.append("Make me a plan")
    return chips + ["Check another job"]


def analysis_messages(result: dict) -> list[dict]:
    msgs = [{"text": result["verdict"] + (f" ({result['fit_percent']}% of the skills it names)"
                                          if result["fit_percent"] is not None else "")}]
    failed = [h for h in result["hard_requirements"] if not h["ok"]]
    passed = [h for h in result["hard_requirements"] if h["ok"]]
    if failed:
        msgs.append({"text": "This one has a requirement studying won't fix: " + "; ".join(h["why"] for h in failed) + "."})
    elif passed:
        msgs.append({"text": "Requirements check out: " + "; ".join(h["why"] for h in passed) + "."})
    for c in result.get("certifications", []):
        msgs.append({"text": f"Mandatory certification: {c['skill']} (the job says: \"{c['requirement'].lstrip('•● ').rstrip('. ')}\"). " +
                     ("You have it ✓" if c["have"] else "You don't have it yet. It's an exam you'd need to pass "
                      "(usually paid), so worth it only if you want this kind of role.")})
    if result["matched"]:
        msgs.append({"text": "You already have: " + ", ".join(f"{m['skill']} ({m['evidence'].split(',')[0]})"
                                                              for m in result["matched"][:6]) + "."})
    if result["missing_required"] and not failed:
        msgs.append({"text": "To be a strong fit, learn: " + ", ".join(f"{m['skill']} ({m['effort']})"
                                                                       for m in result["missing_required"][:4]) + ".",
                     "links": [{"title": f"{m['skill']}: {m['resources'][0]['title']}", "url": m["resources"][0]["url"]}
                               for m in result["missing_required"][:4]]})
    if result["missing_nice"]:
        msgs.append({"text": "Nice to have, not required: " + ", ".join(m["skill"] for m in result["missing_nice"][:4]) + "."})
    return msgs


def learn_message(skill: str, result: dict | None, profile: dict) -> dict:
    info = SKILLS[skill]
    gap = next((m for m in (result or {}).get("missing_required", []) + (result or {}).get("missing_nice", [])
                if m["skill"] == skill), None)
    project = next((re.split(r"\s+[-:]\s+", p.get("title", ""))[0] for p in profile.get("projects") or []), "your best project")
    show = gap["show"] if gap else info["show"].replace("{project}", project)
    return {"text": f"{skill}: about {info['effort']} for you. Pick any of these, then: {show}.", "links": _links(skill)}


# "so should I apply?", "is it worth applying", "am I eligible / a good fit", "apply or not"
SHOULD_APPLY = re.compile(r"\b(should i (apply|go for it|try)|is it worth|worth (applying|it|a try)|am i (eligible|a (good |right )?fit|fit)|"
                          r"do i (fit|qualify)|apply or not|can i apply|good fit)\b")


def apply_message(result: dict) -> dict:
    """"Should I apply?": the verdict and its reasons, straight from the analysis (works without Ollama)."""
    failed = [h["why"] for h in result["hard_requirements"] if not h["ok"]]
    certs = [c["skill"] for c in result.get("certifications", []) if not c["have"]]
    gaps = [m["skill"] for m in result["missing_required"]]
    if failed:
        text = f"I'd skip this one: {'; '.join(failed)}. That's a requirement studying won't fix."
    elif result["verdict"].startswith("Apply"):
        text = "Yes, apply" + (f", and brush up {', '.join(gaps[:2])} before the interview." if gaps else ": you cover what it asks for.")
    elif result["verdict"].startswith("Stretch"):
        text = (f"It's a stretch: you'd need {', '.join(gaps[:3])}. Apply anyway if the role excites you (freshers get "
                "shortlisted with gaps), and start learning the first one now.")
    else:
        text = "I couldn't judge the skills from this description, so read the requirements once yourself; nothing I can check rules you out."
    if certs:
        text += f" Note: it calls {', '.join(certs)} certification mandatory, and you don't have it yet."
    return {"text": text}


def gaps_message(result: dict) -> dict:
    """"Where am I lacking?": straight from the analysis (never guessed by the LLM)."""
    parts = []
    failed = [h["why"] for h in result["hard_requirements"] if not h["ok"]]
    if failed:
        parts.append("Requirements studying won't fix: " + "; ".join(failed) + ".")
    certs = [c["skill"] for c in result.get("certifications", []) if not c["have"]]
    if certs:
        parts.append("Mandatory certification you don't have: " + ", ".join(certs) + ".")
    if result["missing_required"]:
        parts.append("Skills it requires that your profile doesn't show: " +
                     ", ".join(f"{m['skill']} ({m['effort']})" for m in result["missing_required"]) + ".")
    if result["missing_nice"]:
        parts.append("Nice to have: " + ", ".join(m["skill"] for m in result["missing_nice"]) + ".")
    if not parts:
        return {"text": "From what I can check, nothing required is missing. "
                        "I only know the skills on my list, so read the requirements once yourself too."}
    links = [{"title": f"{m['skill']}: {m['resources'][0]['title']}", "url": m["resources"][0]["url"]}
             for m in result["missing_required"][:4]]
    return {"text": "\n".join(parts), "links": links}


def project_message(result: dict) -> dict:
    counts = {}
    for m in result["matched"]:
        for where in m["evidence"].split(", "):
            if where != "your skills" and not where.startswith("certification"):
                counts.setdefault(where, []).append(m["skill"])
    if not counts:
        return {"text": "None of your projects uses the skills this job names; mention your skills list instead."}
    best, skills = max(counts.items(), key=lambda kv: len(kv[1]))
    return {"text": f"Talk about {best}: it shows {', '.join(skills)}, which this job asks for."}


def plan_message(plan: dict, notes: str = "") -> dict:
    """The current plan in words, with a first free resource per topic."""
    if not plan or not plan.get("items"):
        return {"text": "Nothing required is missing, so no plan needed: polish your resume and apply!"}
    status = "It's in your calendar ✓" if plan.get("in_calendar") else "It's not in your calendar yet."
    text = (notes + "\n\n" if notes else "") + "Your plan:\n" + octo_plan.describe(plan) + "\n" + status
    links = [{"title": f"{it['skill']}: {link['title']}", "url": link["url"]}
             for it in plan["items"] for link in topic_links(it["skill"])[:1]]
    return {"text": text, "links": links}


def plan_chips(plan: dict | None) -> list[str]:
    chips = []
    if plan and not plan.get("in_calendar"):
        chips.append("Add this plan to my calendar")
    if plan and any(it["days"] < it.get("asked_days", it["days"]) for it in plan["items"]):
        chips.append("Keep the full days")
    return chips + ["Show me tutorials", "Check another job"]


def status_message(plan: dict | None) -> dict:
    """"Did you change it / add it?": the facts, never the LLM's guess."""
    if not plan:
        return {"text": "There's no plan yet. Tell me what you want to learn and for how long, e.g. "
                        "\"LangChain in 2 days, then PySpark for 5 days, from 20 to 24 October\"."}
    where = ("Yes, it's in your calendar." if plan.get("in_calendar")
             else "It's NOT in your calendar yet: say \"add this plan to my calendar\" and I will.")
    return {"text": "This is your plan now:\n" + octo_plan.describe(plan) + "\n" + where}


def tutorials_message(result: dict | None, history: list[dict] | None = None) -> dict:
    """Resources for what we were just talking about (Octo's last reply), else for this job's gaps."""
    topics = context_topics(history or [], result)
    if not topics:
        return {"text": "Tell me which skill you want to learn, e.g. \"How do I learn Docker?\", "
                        "or paste a job description first."}
    links = [{"title": f"{t}: {link['title']}", "url": link["url"]} for t in topics for link in topic_links(t)[:3]]
    return {"text": f"Here are free ones for {', '.join(topics)}: freeCodeCamp first, then a specialist channel and "
                    "Coursera (audit for free). They're searches, so you can pick the newest video.", "links": links}


def calendar_message(plan: dict | None, message: str) -> tuple[dict, dict | None]:
    """Agent tool: write the plan into Google Calendar (the spare account GoForIt uses).
    Returns (message, plan) with plan["in_calendar"] set once it's really there."""
    from services import google_auth, study_plan
    if not plan or not plan.get("items"):
        return {"text": "There's no plan to add yet: paste a job description, or tell me what to learn and when."}, plan
    try:
        service = google_auth.service("calendar", "v3")
        existing = study_plan.existing_plan(service)
        both = bool(BOTH.search(message))
        replace = re.search(r"\b(replace|redo|overwrite)\b", message, re.I) and not both
        if existing and not replace and not both:
            now = "\n".join(_calendar_line(r) for r in study_plan.plan_dates(service))
            return {"text": "Your calendar already has an Agent Octo plan" + (f":\n{now}" if now else ".") +
                            "\n\nAdd this one alongside it, or replace it?\n" + octo_plan.describe(plan),
                    "chips": ["Add it alongside", "Yes, replace my plan", "Keep my current plan"]}, plan
        if existing and replace:
            study_plan.remove_plan(service)
        study_plan.add_custom_plan(service, plan, topic_links)
    except google_auth.SignInNeeded:
        return {"text": "I need you to sign in to Google once: double-click check-jobs.bat, then ask me again."}, plan
    except Exception as err:  # network down, Google hiccup
        return {"text": f"I couldn't reach Google Calendar ({type(err).__name__}). Try again in a bit."}, plan
    plan = dict(plan, in_calendar=True)
    return {"text": "Done! It's in your calendar, with a 10-minute reminder and free course links in each event:\n"
                    + octo_plan.describe(plan)}, plan


# "Keep both": add the new plan next to what's already in the calendar.
BOTH = re.compile(r"\b(both|alongside|as well|in addition|additionally|no need to replace|don.?t replace|do not replace|"
                  r"without replacing|keep (it|that|the old|the other|my old)|add (it|this) (also|too))\b", re.I)
# "Yes add it", "go ahead", "schedule it": the plan we're talking about goes into the calendar.
ADD_IT = re.compile(r"^\s*(yes|yeah|ya|ok|okay|sure)?[\s,!.]*(please\s+)?(add|put|schedule|save|book)\s+(it|this|that|them|the plan)\b|"
                    r"^\s*(yes|yeah|ya|ok|okay|sure)?[\s,!.]*(go ahead|do it)\b", re.I)


def _calendar_line(r: dict) -> str:
    """"• Spark: 21 Oct – 24 Oct, 8 PM" from a plan_dates row."""
    name = r["summary"].replace(" (Agent Octo plan)", "").replace("📚 ", "").replace("Learn ", "")
    when = _day(r["first"]) + (f" – {_day(r['last'])}" if r["last"] != r["first"] else "")
    t = r.get("time") or ""
    if t[:2].isdigit():
        h = int(t[:2])
        when += f", {h % 12 or 12} {'AM' if h < 12 else 'PM'}"
    return f"• {name}: {when}"


def _day(iso: str) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(iso)
        return f"{d.day} {d:%b}"
    except ValueError:
        return iso or "?"


def calendar_dates_message(plan: dict | None) -> dict:
    """"Which dates did you add?": read from the calendar itself."""
    from services import google_auth, study_plan
    try:
        rows = study_plan.plan_dates(google_auth.service("calendar", "v3"))
    except google_auth.SignInNeeded:
        return {"text": "I need you to sign in to Google once (double-click check-jobs.bat) before I can look."}
    except Exception as err:
        return {"text": f"I couldn't reach Google Calendar ({type(err).__name__}). Try again in a bit."}
    if not rows:
        extra = " Your current plan isn't added yet." if plan else ""
        return {"text": "There's no Agent Octo study plan in your calendar from today on." + extra}
    lines = [_calendar_line(r) + f" ({r['count']} session{'s' * (r['count'] != 1)})" for r in rows]
    return {"text": "In your calendar right now:\n" + "\n".join(lines)}


def jobs_message() -> dict:
    """Agent tool: today's best open jobs from the Excel tracker the daily scan fills."""
    from app import config
    from services.study_plan import todays_jobs
    from services.tracker_xlsx import load_rows
    if not config.TRACKER_PATH.exists():
        return {"text": "I can't find your job tracker yet: run check-jobs.bat once."}
    try:
        picks = todays_jobs(list(load_rows(config.TRACKER_PATH).values()))
    except PermissionError:
        return {"text": "Your tracker is open in Excel: close it and ask me again."}
    if not picks:
        return {"text": "No open High/Medium-fit jobs right now. I'll have more after tomorrow's 8:30 scan."}
    lines = []
    for i, r in enumerate(picks, 1):
        warn = f" · ⚠ {r['experience_signal']}" if str(r.get("experience_signal", "")).startswith("Asks") else ""
        lines.append(f"{i}. {r.get('title')} at {r.get('company')} ({r.get('location') or 'location n/a'}) · "
                     f"{str(r.get('fit_score')).split(' (')[0]} fit{warn}")
    return {"text": "Your best open jobs right now:\n" + "\n".join(lines) +
                    "\nOpen one, copy its description and paste it here: I'll check it properly.",
            "links": [{"title": f"{r.get('title')} – {r.get('company')}"[:60], "url": r["link"]} for r in picks if r.get("link")]}


OCTO_SYSTEM = """You are Agent Octo, a friendly, honest career mentor (an octopus) for an Indian engineering student.
Answer in 2-5 short sentences, warm but direct. Use ONLY the facts given about the student and the job.
Never invent the student's skills, projects, experience, marks or achievements. When you talk about the
student's fit for the pasted job, use ONLY its requirement lines and the analysis, and say the student has a
skill only if it is under "Matched". Questions about anything else (other companies, tools, terms, roles)
are fine: answer them normally. You can't change plans or the calendar yourself: never say you
changed, added, adjusted or scheduled anything. Never write URLs or links:
refer to resources only by the names given. If you don't know, say so."""


EXPLAIN_SYSTEM = """You are Agent Octo, a friendly career mentor for an Indian engineering student.
Explain the term the student asks about in 3-5 short, plain sentences: what it is, what people in that kind of
job do day to day, and what a fresher usually needs to learn first. If it is a company's job role, say what the
role usually involves. If you are not sure what the term means, say so instead of guessing. No links, no lists
of more than 4 items, and nothing about the student's own skills."""

# "what is SAP Technical?", "explain RAG", "meaning of ITSM", "what does a data engineer do"
EXPLAIN = re.compile(r"^\s*(what|wht|wat)\s+(is|are|r|does|do)\b|\bexplain\b|\bmeaning of\b|\bwhat do (you|u) mean by\b|"
                     r"\bwhat.?s (a |an |the )?\w|\btell me (about|what)\b|"
                     r"\bwhat (do|does|will) (they|it|that|this|an?|the) ?\w* ?(role|job|team|people|engineers?|developers?)? ?do\b|"
                     r"\bwhat is (an? |the )?\w+", re.I)
# ...but "what is MY fit / am I ready / should I apply to THIS job" is about the student: that one stays
# with the job-aware answer.
ABOUT_ME = re.compile(r"\b(my (fit|chances?|profile|skills?|resume|plan|score)|am i|do i|should i|can i|will i|"
                      r"this job|the job|this role|for me)\b")


def _topic_of(message: str) -> str:
    """The term asked about: "what is SAP TECHNICAL?" -> "SAP TECHNICAL"."""
    t = re.sub(r"^\s*(what|wht|wat)\s+(is|are|r|does|do)\s+|^.*?\b(explain|meaning of|mean by|tell me about|tell me what)\s+|"
               r"^\s*what.?s\s+", "", message.strip(), flags=re.I)
    t = re.sub(r"\b(a|an|the)\s+", "", t, count=1, flags=re.I)
    return re.split(r"[?.!,\n]| and | in | for | at | like ", t)[0].strip()[:60]


def explain_message(message: str, history: list[dict]) -> dict:
    """A general explanation (not limited to the pasted job), with free learning links."""
    skill = _skill_in(message)
    topic = skill or _topic_of(message)
    # Known skills: free videos/courses + the official free site (e.g. SAP Learning); others: free searches.
    links = [{"title": f"{skill or topic}: {link['title']}", "url": link["url"]} for link in topic_links(topic)[:5]] if topic else []
    if not ollama_client.ollama_running():
        return {"text": f"My chatty brain (Ollama) is off, so I can't explain {topic or 'that'} right now, but these "
                        "free resources start from the basics:" if links else
                        "My chatty brain (Ollama) is off right now, so I can't explain that.", "links": links}
    turns = "\n".join(f"{h.get('role', 'user')}: {h.get('text', '')[:300]}" for h in history[-4:])
    text, _ = ollama_client.chat(EXPLAIN_SYSTEM, (f"Conversation so far:\n{turns}\n\n" if turns else "") +
                                 f"Student asks: {message}", temperature=0.3)
    text = re.sub(r"https?://\S+|www\.\S+", "", text).strip()
    if CLAIMS_ACTION.search(text) or not text:
        text = f"I'm not sure how to explain {topic or 'that'} well: these free resources start from the basics."
    return {"text": text, "links": links}


CLAIMS_ACTION = re.compile(r"\b(is now in|now (in|on) your|i.?ve (added|scheduled|updated|changed|adjusted|put)|i (added|scheduled|"
                           r"updated|changed|adjusted|put)|has been (added|scheduled|updated)|(added|scheduled) (it|this|the plan)|"
                           r"adjusted the plan)\b", re.I)


# Messages about the pasted job (only then does the local AI get the job analysis).
JOB_TALK = re.compile(r"\b(job|jd|role|position|opening|vacancy|fit|apply|applying|application|requirements?|eligib\w*|"
                      r"shortlist\w*|interview|company|this one|chances?|selected|hiring)\b", re.I)


def _similar(a: str, b: str) -> bool:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.75


def profile_message(message: str, profile: dict) -> dict | None:
    """"List my skills / projects / certifications / achievements": straight from the profile."""
    low = message.lower()
    facts = safe_profile(profile)
    if re.search(r"\bskill", low):
        groups = {"languages": "Languages", "ml_ai": "ML / AI", "web": "Web", "databases": "Databases", "tools": "Tools"}
        lines = [f"{groups.get(k, k.replace('_', ' ').title())}: {', '.join(v)}" for k, v in facts["skills"].items() if v]
        return {"text": "Your skills (from your profile):\n" + "\n".join(lines) if lines
                else "Your profile has no skills yet: add them under Edit profile → Skills."}
    if re.search(r"\bproject", low):
        lines = [f"• {pr.get('title')}" + (f" ({', '.join(pr.get('tech') or [])})" if pr.get("tech") else "")
                 for pr in facts["projects"] if pr.get("title")]
        return {"text": "Your projects:\n" + "\n".join(lines) if lines else "Your profile has no projects yet."}
    if re.search(r"\bcertific", low):
        lines = [f"• {c.get('name')}" + (f" ({c.get('issuer')})" if c.get("issuer") else "") for c in facts["certifications"] if c.get("name")]
        return {"text": "Your certifications:\n" + "\n".join(lines) if lines else "Your profile has no certifications yet."}
    if re.search(r"\bachievement", low):
        lines = [f"• {a}" for a in facts["achievements"] if a]
        return {"text": "Your achievements:\n" + "\n".join(lines) if lines else "Your profile has no achievements yet."}
    if re.search(r"\bexperience|internship", low):
        lines = [f"• {e.get('role')} at {e.get('company')}" for e in facts["experience"] if e.get("company")]
        return {"text": "Your experience:\n" + "\n".join(lines) if lines else "Your profile has no work experience yet (that's fine for a fresher)."}
    return None


# "list my skills", "what are my projects", "show my certifications", "my technical skillsets"
MY_PROFILE = re.compile(r"\b(list|show|what are|what r|tell me|give me|which are)?\b.*\bmy\s+(technical\s+|tech\s+|current\s+)?"
                        r"(skills?|skill ?sets?|projects?|certifications?|certificates?|achievements?|experience|internships?)\b", re.I)


def llm_message(message: str, profile: dict, result: dict | None, history: list[dict], plan: dict | None = None) -> dict:
    facts = safe_profile(profile)
    skills = sorted({s for group in facts["skills"].values() for s in group})
    context = [f"Student: {facts['degree'].get('name', '')} {facts['degree'].get('branch', '')}, graduating "
               f"{facts['degree'].get('graduation_year', '')}. Skills: {', '.join(skills)}.",
               "Projects: " + "; ".join(p.get("title", "") for p in facts["projects"])]
    if result and JOB_TALK.search(message):
        context.append(f"Current job analysis: {result['verdict']}. Matched: {', '.join(m['skill'] for m in result['matched'])}. "
                       f"Missing: {', '.join(m['skill'] for m in result['missing_required'])}.")
        if result.get("requirements"):
            context.append("Job requirement lines: " + " | ".join(result["requirements"][:15]))
        names = sorted({r['title'] for m in result["missing_required"] for r in m["resources"]})
        if names:
            context.append("Resources you may name: " + "; ".join(names))
    if plan and plan.get("items"):
        context.append("Current study plan (" + ("in" if plan.get("in_calendar") else "NOT in") + " the calendar): "
                       + octo_plan.describe(plan).replace("\n", "; "))
    turns = "\n".join(f"{h.get('role', 'user')}: {h.get('text', '')[:400]}" for h in history[-6:])
    prompt = "\n".join(context) + (f"\n\nConversation so far:\n{turns}" if turns else "") + f"\n\nStudent: {message}"
    text, _ = ollama_client.chat(OCTO_SYSTEM, prompt, temperature=0.4)
    last = next((h.get("text", "") for h in reversed(history) if h.get("role") == "octo"), "")
    if last and _similar(text, last):
        # Small models like to repeat their previous answer. Ask once more, about the NEW message only.
        text, _ = ollama_client.chat(OCTO_SYSTEM, "\n".join(context) + f"\n\nAnswer this new message directly. Do not repeat "
                                     f"your previous answer (\"{last[:200]}\").\n\nStudent: {message}", temperature=0.7)
    text = re.sub(r"https?://\S+|www\.\S+", "", text).strip()  # links only ever come from the curated list
    if CLAIMS_ACTION.search(text):
        # It said it added / changed / scheduled something. It can't, so don't let it pretend.
        return {"text": "I haven't changed anything. To put the plan in your calendar, say \"add this plan to my "
                        "calendar\"; to change it, tell me what to learn, how many days, the dates or the time "
                        "(e.g. \"LangChain 2 days from 21 Oct at 11 am\")."}
    return {"text": text or "I'm not sure about that one."}


def reply(message: str, profile: dict, result: dict | None = None, history: list[dict] | None = None,
          job_title: str = "", plan: dict | None = None) -> dict:
    """{"messages": [{text, links?}], "mood", "chips", "result" (if a new job was checked), "plan"}.
    The plan goes back to the side panel every time, which sends it with the next message."""
    out = _reply(message, profile, result, history, job_title, plan)
    out.setdefault("plan", plan)
    return out


def _reply(message: str, profile: dict, result: dict | None, history: list[dict] | None,
           job_title: str, plan: dict | None) -> dict:
    message = (message or "").strip()
    history = history or []
    low = message.lower()
    if looks_like_job_description(message):
        result = coach(message, profile, job_title)
        # A new job: its default plan (missing skills, one after another) replaces the old one.
        return {"messages": analysis_messages(result), "mood": result["mood"], "chips": _chips(result), "result": result,
                "plan": octo_plan.plan_from_gaps(result) if result["missing_required"] else None}
    if re.search(r"\b(another job|new job|check (a|another))\b", low):
        return {"messages": [{"text": "Sure! Paste the next job description (Ctrl+A, Ctrl+C on the job page)."}],
                "mood": "idle", "chips": []}
    if re.search(r"\b(what can you do|help|who are you)\b", low):
        return {"messages": [{"text": "I'm Agent Octo. Paste a job description and I'll tell you if it's a fit, what you "
                                      "already have, what to learn (free videos and courses) and which project to mention. "
                                      "I can also pick today's jobs from your tracker and put a learning plan in your calendar."}], "mood": "happy", "chips": _chips(result)}
    if re.search(r"\b(which|what) jobs?\b|\bjobs? (for )?today\b|\bapply (to )?today\b|\btoday.?s jobs\b|\bmy jobs\b", low):
        return {"messages": [jobs_message()], "mood": "happy", "chips": _chips(result)}
    if re.search(r"\b(which|what) (dates?|days?|time)\b|\bwhen (is|are|did|do|does)\b|\bwhat.?s (in|on) my calendar\b|"
                 r"\bshow (me )?my calendar\b", low):
        return {"messages": [calendar_dates_message(plan)], "mood": "idle", "chips": plan_chips(plan)}
    if re.search(r"\bdid (you|u) (really )?(change|update|edit|fix|add|put|save|make|do)\b|\bis it (in|on) (my )?calendar\b", low):
        return {"messages": [status_message(plan)], "mood": "idle", "chips": plan_chips(plan)}
    if plan and re.search(r"\bkeep (the )?(full )?days\b", low):
        plan = octo_plan.keep_full_days(plan)
        return {"messages": [plan_message(plan, "Okay, full days: the end date moves.")], "mood": "happy",
                "chips": plan_chips(plan), "plan": plan}
    wants_both = BOTH.search(low) and re.search(r"\b(add|schedule|put|keep|do|calendar|replace)\b", low)
    if re.search(r"\bcalendar\b|\breplace my plan\b", low) or (plan and (ADD_IT.search(low) or wants_both)):
        plan = plan or (octo_plan.plan_from_gaps(result) if result else None)
        if plan and octo_plan.parse_hour(message):           # "add it to my calendar at 7 pm"
            plan = dict(plan, hour=octo_plan.parse_hour(message))
        msg, plan = calendar_message(plan, message)
        return {"messages": [msg], "mood": "happy" if msg["text"].startswith("Done") else "idle",
                "chips": msg.pop("chips", None) or plan_chips(plan), "plan": plan}
    if re.search(r"\bkeep my (current )?plan\b", low):
        return {"messages": [{"text": "Okay, I left your calendar as it is."}], "mood": "idle", "chips": plan_chips(plan)}
    if octo_plan.wants_plan_change(message, plan):
        plan, notes = octo_plan.update_plan(message, plan, result)
        return {"messages": [plan_message(plan, notes or "Done, I changed the plan.")], "mood": "happy",
                "chips": plan_chips(plan), "plan": plan}
    if MY_PROFILE.search(message) and not re.search(r"\b(improve|add|missing|lack|need|should)\b", low):
        msg = profile_message(message, profile)
        if msg:
            return {"messages": [msg], "mood": "happy", "chips": _chips(result)}
    skill = _skill_in(message)
    pointing = re.search(r"\b(learn|study|start|do) (that|this|it|those|these|them)\b", low)
    if not skill and (pointing or re.search(r"\b(tutorials?|videos?|youtube|courses?|coursera|resources?|links?|freecodecamp)\b", low)):
        return {"messages": [tutorials_message(result, history)], "mood": "happy", "chips": _chips(result)}
    if skill and re.search(r"\b(learn|study|start|resources?|course|how|improve|get better|practice|tutorials?|videos?)\b", low):
        return {"messages": [learn_message(skill, result, profile)], "mood": "happy", "chips": _chips(result)}
    if result and SHOULD_APPLY.search(low):
        return {"messages": [apply_message(result)], "mood": result["mood"], "chips": _chips(result)}
    if result and re.search(r"\b(lacking|lack|missing|gaps?|weak|short of|don.?t have|need to learn|what (else|more) do i need)\b", low):
        return {"messages": [gaps_message(result)], "mood": "idle", "chips": _chips(result)}
    if result and re.search(r"\b(which|what) project", low):
        return {"messages": [project_message(result)], "mood": "happy", "chips": _chips(result)}
    if (plan or result) and re.search(r"\bplan\b|\broadmap\b|\bschedule\b", low):
        plan = plan or octo_plan.plan_from_gaps(result)
        return {"messages": [plan_message(plan)], "mood": "happy", "chips": plan_chips(plan), "plan": plan}
    # ("what is MY fit / THIS job" is about the student: that stays with the job-aware answer below)
    if EXPLAIN.search(message) and not ABOUT_ME.search(low):
        try:
            return {"messages": [explain_message(message, history)], "mood": "happy", "chips": _chips(result)}
        except (OSError, ValueError, KeyError):
            pass  # the local AI didn't answer: fall through to the usual message
    if not ollama_client.ollama_running():
        return {"messages": [{"text": "My chatty brain (Ollama) is off right now. I can still check a pasted job "
                                      "description, or tell you how to learn a skill: try \"How do I learn Docker?\""}],
                "mood": "concerned", "chips": _chips(result)}
    try:
        return {"messages": [llm_message(message, profile, result, history, plan)], "mood": "idle", "chips": _chips(result)}
    except (OSError, ValueError, KeyError):
        return {"messages": [{"text": "I couldn't think that one through (the local AI didn't answer). Try again?"}],
                "mood": "concerned", "chips": _chips(result)}
