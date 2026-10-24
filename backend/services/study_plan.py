"""Octo's tools: put a learning plan in Google Calendar, and pick today's jobs from the tracker.

Calendar: the spare Google account GoForIt already uses for job reminders (scope calendar.events).
Each topic of the plan (agents/octo_plan.py) gets ONE daily recurring event for its days,
at the plan's hour (default 8-9 PM). Events are tagged (private property goforitStudy=1) so a second "add my plan"
can find them and ask before replacing. Only skill names and public course links go into the
events: no profile data.
"""

from datetime import date, datetime

from app import config

TAG = {"privateExtendedProperty": "goforitStudy=1"}


def existing_plan(service) -> list[dict]:
    """GoForIt study events from today on."""
    now = datetime.utcnow().isoformat() + "Z"
    items = service.events().list(calendarId="primary", timeMin=now, singleEvents=False, maxResults=50, **TAG).execute()
    return items.get("items", [])


def remove_plan(service) -> int:
    events = existing_plan(service)
    for e in events:
        service.events().delete(calendarId="primary", eventId=e["id"]).execute()
    return len(events)


def todays_jobs(rows: list[dict], limit: int = 5) -> list[dict]:
    """Open High/Medium jobs from the tracker, High first, newest first; probably-expired ones left out."""
    from services.calendar_reminders import is_open, probably_expired
    picks = [r for r in rows
             if is_open(r) and not probably_expired(r) and str(r.get("fit_score") or "").split(" ")[0] in ("High", "Medium")]
    picks.sort(key=lambda r: (str(r.get("fit_score", "")).startswith("High"), str(r.get("posted") or r.get("received") or "")),
               reverse=True)
    return picks[:limit]


def add_custom_plan(service, plan: dict, links_for) -> list[dict]:
    """The student's own plan (agents/octo_plan.py): per skill, one daily event for its days.
    links_for(skill) -> [{"title", "url"}] puts free resources in the event."""
    created = []
    hour = plan.get("hour", 20)
    for it in plan["items"]:
        links = "\n".join(f"{link['title']}: {link['url']}" for link in links_for(it["skill"])[:4])
        day = date.fromisoformat(it["start"])
        body = {
            "summary": f"📚 Learn {it['skill']} (Agent Octo plan)",
            "description": f"{it['days']} day(s) of {it['skill']}.\n\n{links}\n\nPlanned by GoForIt's Agent Octo.",
            "start": {"dateTime": f"{day.isoformat()}T{hour:02d}:00:00", "timeZone": config.TIMEZONE},
            "end": {"dateTime": f"{day.isoformat()}T{hour + 1:02d}:00:00", "timeZone": config.TIMEZONE},
            "recurrence": [f"RRULE:FREQ=DAILY;COUNT={it['days']}"],
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
            "extendedProperties": {"private": {"goforitStudy": "1"}},
        }
        created.append(service.events().insert(calendarId="primary", body=body).execute())
    return created


def plan_dates(service) -> list[dict]:
    """What's really in the calendar: [{"summary", "first", "last", "count"}] per study topic, upcoming."""
    now = datetime.utcnow().isoformat() + "Z"
    items = service.events().list(calendarId="primary", timeMin=now, singleEvents=True, orderBy="startTime",
                                  maxResults=200, **TAG).execute().get("items", [])
    out = {}
    for e in items:
        start = e.get("start") or {}
        when = start.get("dateTime", "")[:10] or start.get("date", "")
        clock = start.get("dateTime", "")[11:16]   # "20:00"
        row = out.setdefault(e.get("summary", "Study"), {"summary": e.get("summary", "Study"), "first": when, "last": when,
                                                         "count": 0, "time": clock})
        row["last"], row["count"] = when, row["count"] + 1
    return list(out.values())
