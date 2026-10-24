"""Agent Octo's study plan, as real state the student can edit in plain words.

The plan travels with the chat (the side panel sends it back with every message), so Octo can
answer "did you change it?" from facts instead of letting the LLM guess. Understood without AI:

  "I don't want Airflow, I'm talking about LangChain and PySpark"   -> plan = LangChain, Spark
  "LangChain in 2 days and PySpark for 5 days, from 20 to 24 October" -> those days, those dates
  "at 7 pm" -> study time;  "keep the days" -> don't squeeze into the end date

Plan = {"items": [{"skill", "start", "days", "asked_days"}], "start", "end", "hour", "in_calendar"}
with dates as "YYYY-MM-DD". Each item is studied on consecutive days, one after another.
"""

import re
from datetime import date, timedelta

from services.learning_resources import SKILLS
from services.option_match import words

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
NEGATION = re.compile(r"\b(?:don.?t|do not|dont|not|no|skip|remove|drop|without|except)\b(?:\s+(?:want|need|like|to|learn|do|study|include|the|any)){0,4}\s+$")
PLAN_WORDS = re.compile(r"\b(plan|schedule|roadmap|days?|weeks?|talking about|instead|only|focus on|from|till|until|starting|"
                        r"by|calendar|don.?t want|dont want|do not want)\b")


def _aliases(name: str) -> list[str]:
    return [name] + SKILLS[name]["aliases"]


def _find(text: str) -> list[tuple[int, int, str]]:
    """(start, end, skill) for each curated skill named in text (lower-case words), first mention."""
    t = f" {words(text)} "
    out = []
    for name in SKILLS:
        spots = [(t.find(f" {words(a)} "), len(words(a))) for a in _aliases(name) if f" {words(a)} " in t]
        if spots:
            pos, length = min(spots)
            out.append((pos, pos + length + 1, name))
    return sorted(out)


def _default_days(skill: str) -> int:
    """Rough days from the curated effort ("a few days" -> 3, "1-2 weeks" -> 7, "2-3 weeks" -> 10)."""
    effort = SKILLS[skill]["effort"]
    if "few days" in effort or "weekend" in effort:
        return 3
    m = re.search(r"(\d+)(?:-\d+)?\s*weeks?", effort)
    return {1: 5, 2: 7}.get(int(m.group(1)), 10) if m else 5


def _year_for(month: int, day: int, today: date) -> date:
    d = date(today.year, month, day)
    return d if d >= today - timedelta(days=31) else date(today.year + 1, month, day)


def parse_dates(text: str, today: date) -> tuple[date | None, date | None]:
    """"from 20 october to 24 october", "20-24 oct", "oct 20 to oct 24", "starting 22 oct", "till 30 nov"."""
    low = text.lower()
    found = []
    for m in re.finditer(rf"\b{DAY}\s*(?:-|–|to)\s*{DAY}\s+(?:of\s+)?{MONTH}", low):          # 20-24 oct
        mon = MONTHS[m.group(3)[:3]]
        return _year_for(mon, int(m.group(1)), today), _year_for(mon, int(m.group(2)), today)
    for m in re.finditer(rf"\b{DAY}\s+(?:of\s+)?{MONTH}|\b{MONTH}\s+{DAY}\b", low):
        day, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        try:
            found.append((m.start(), _year_for(MONTHS[mon[:3]], int(day), today)))
        except ValueError:  # "31 nov"
            continue
    if not found:
        return None, None
    if len(found) == 1:
        before = low[:found[0][0]]
        if re.search(r"\b(till|until|by|before|end(ing)?( on)?)\s*$", before):
            return None, found[0][1]
        return found[0][1], None
    return found[0][1], found[-1][1]


def parse_hour(text: str) -> int | None:
    # The LAST time mentioned is the one asked for: "Spark is 8 pm, schedule this at 11am" -> 11.
    found = list(re.finditer(r"\b(\d{1,2})(?::00)?\s*(am|pm)\b", text.lower()))
    if not found:
        return None
    m = found[-1]
    hour = int(m.group(1)) % 12 + (12 if m.group(2) == "pm" else 0)
    return hour if 5 <= hour <= 22 else None


def wants_plan_change(message: str, plan: dict | None) -> bool:
    """A message about WHAT to study / for how long / when (not "how do I learn X?")."""
    low = message.lower()
    named = _find(message)
    if not named:
        return bool(plan) and bool(parse_dates(message, date.today())[0] or parse_hour(message))
    padded = f" {words(message)} "
    if any(NEGATION.search(padded[:pos + 1]) for pos, end, name in named):
        return True   # "skip Airflow", "I don't want Docker"
    if re.search(r"\bhow (do|can|should) i\b", low) and not re.search(r"\b(days?|weeks?|plan|schedule)\b", low):
        return False
    return bool(PLAN_WORDS.search(low))


def _schedule(items: list[dict], start: date) -> None:
    day = start
    for it in items:
        it["start"] = day.isoformat()
        day += timedelta(days=it["days"])


def update_plan(message: str, plan: dict | None, result: dict | None, today: date | None = None) -> tuple[dict, str]:
    """Apply the student's words to the plan. Returns (new plan, what changed, in words)."""
    today = today or date.today()
    low = f" {words(message)} "
    named = _find(message)
    negated = {name for pos, end, name in named if NEGATION.search(low[:pos + 1])}
    wanted = [name for pos, end, name in named if name not in negated]

    old = [dict(it) for it in (plan or {}).get("items", [])]
    if wanted:
        # Naming skills says what the plan is about: keep their old days unless new ones are given.
        old_days = {it["skill"]: it.get("asked_days", it["days"]) for it in old}
        items = [{"skill": s, "days": old_days.get(s, _default_days(s))} for s in wanted]
    else:
        base = old or [{"skill": m["skill"], "days": _default_days(m["skill"])}
                       for m in (result or {}).get("missing_required", [])[:4] if m["skill"] in SKILLS]
        items = [it for it in base if it["skill"] not in negated]

    # "<skill> within 2 days", "<skill> for 1 week": a number after the skill (before the next skill).
    bounds = [(pos, end, name) for pos, end, name in named if name not in negated]
    for i, (pos, end, name) in enumerate(bounds):
        stop = bounds[i + 1][0] if i + 1 < len(bounds) else len(low)
        m = re.search(r"\b(\d{1,2})\s*(days?|weeks?)\b", low[end:stop])
        if m:
            n = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
            for it in items:
                if it["skill"] == name:
                    it["days"] = max(1, min(n, 60))
    for it in items:
        it["asked_days"] = it["days"]

    start, end = parse_dates(message, today)
    start = start or (date.fromisoformat(plan["start"]) if plan and plan.get("start") else None)
    if not start:
        start = today + timedelta(days=1)
    if end is None and plan and plan.get("end") and not parse_dates(message, today)[0]:
        end = date.fromisoformat(plan["end"])
    hour = parse_hour(message) or (plan or {}).get("hour") or 20

    notes = []
    if negated:
        notes.append("Removed " + ", ".join(sorted(negated)) + ".")
    if end:
        span = (end - start).days + 1
        total = sum(it["days"] for it in items)
        if total > span > 0:
            # Too much for the dates: shorten the longest topics first, never below 1 day each.
            while sum(it["days"] for it in items) > span and any(it["days"] > 1 for it in items):
                max(items, key=lambda it: it["days"])["days"] -= 1
            notes.append(f"That's {total} days of study in {span} days, so I shortened "
                         + ", ".join(f"{it['skill']} to {it['days']} (you said {it['asked_days']})"
                                     for it in items if it["days"] < it["asked_days"]) + ".")
    _schedule(items, start)
    new = {"items": items, "start": start.isoformat(), "end": end.isoformat() if end else None,
           "hour": hour, "in_calendar": False}
    return new, " ".join(notes)


def keep_full_days(plan: dict) -> dict:
    """"Keep the days": use the days the student asked for and let the end date move."""
    items = [dict(it, days=it.get("asked_days", it["days"])) for it in plan["items"]]
    _schedule(items, date.fromisoformat(plan["start"]))
    return dict(plan, items=items, end=None, in_calendar=False)


def _fmt(d: date) -> str:
    return f"{d.day} {d:%b}"


def item_dates(it: dict) -> tuple[date, date]:
    first = date.fromisoformat(it["start"])
    return first, first + timedelta(days=it["days"] - 1)


def describe(plan: dict) -> str:
    lines = []
    for it in plan["items"]:
        first, last = item_dates(it)
        when = _fmt(first) if first == last else f"{_fmt(first)} – {_fmt(last)}"
        lines.append(f"• {it['skill']}: {when} ({it['days']} day{'s' if it['days'] != 1 else ''})")
    hour = plan.get("hour", 20)
    clock = f"{hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"
    return "\n".join(lines) + f"\nOne hour a day at {clock}."


def plan_from_gaps(result: dict, today: date | None = None) -> dict:
    """The default plan for a checked job: its missing required skills, one after another."""
    return update_plan("", None, result, today)[0]
