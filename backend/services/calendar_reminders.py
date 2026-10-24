"""Apply reminders in Google Calendar for High/Medium-fit jobs from the tracker.

Default: ONE event per morning listing all new High/Medium jobs (best first),
so ten jobs don't mean ten notifications. A later run on the same day adds to
that morning's event instead of creating another. `per_job=True` makes one
event per job instead.

Each job line has two signed links, "✓ Applied" and "✗ Expired"
(services/action_links.py). Clicking one updates the tracker and calls
refresh_event(), which re-renders the event from the tracker, so you never
edit the event by hand.

Each job is reminded once: its event id goes into the tracker's Reminder
event column. Only jobs whose Status is New (or empty) are reminded, and
jobs posted long ago are skipped as probably expired.
`service` is a Google Calendar API client (tests pass a fake one).
"""

from datetime import date, datetime, time, timedelta
from html import escape

from app import config
from services import action_links

FITS_TO_REMIND = ("High", "Medium")
DIGEST_KEY = "goforitDigest"  # private property marking our morning events


def probably_expired(row: dict, today: date | None = None) -> bool:
    """Posted longer ago than config.MAX_JOB_AGE_DAYS (we can't check the job page itself)."""
    try:
        posted = datetime.strptime(str(row.get("posted") or row.get("received")), "%Y-%m-%d").date()
    except ValueError:
        return False
    return ((today or date.today()) - posted).days > config.MAX_JOB_AGE_DAYS


def is_open(row: dict) -> bool:
    return str(row.get("status") or "New") == "New"


def wants_reminder(row: dict, today: date | None = None) -> bool:
    fit = str(row.get("fit_score") or "").split(" ")[0]
    return (fit in FITS_TO_REMIND and not row.get("reminder_event")
            and is_open(row) and not probably_expired(row, today))


def reminder_day(row: dict, now: datetime) -> date:
    """The morning after the alert arrived, or the next upcoming morning if that has passed."""
    try:
        day = datetime.strptime(str(row.get("received")), "%Y-%m-%d").date() + timedelta(days=1)
    except ValueError:
        day = now.date() + timedelta(days=1)
    upcoming = now.date() if now.time() < time(config.REMINDER_HOUR) else now.date() + timedelta(days=1)
    return max(day, upcoming)


def _when(day: date) -> dict:
    start = datetime.combine(day, time(config.REMINDER_HOUR))
    return {
        "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": (start + timedelta(minutes=15)).isoformat(), "timeZone": config.TIMEZONE},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    }


def _rank(row: dict) -> int:
    fit = str(row.get("fit_score") or "").split(" ")[0]
    return FITS_TO_REMIND.index(fit) if fit in FITS_TO_REMIND else len(FITS_TO_REMIND)


# ---------- rendering (Google Calendar descriptions accept simple HTML) ----------

def _job_html(row: dict) -> str:
    title = escape(f"{row['title']} @ {row['company']}")
    where = escape(row.get("location") or "location n/a")
    fit = escape(str(row["fit_score"]))
    if not is_open(row):
        mark = {"Applied": "✓", "Scam": "⚑", "Not eligible": "⏳"}.get(str(row.get("status")), "✗")
        return f"{mark} <s>{title}</s> ({escape(str(row['status']))})"
    return (f"• [{fit}] <a href=\"{escape(row['link'])}\">{title}</a> ({where})<br>"
            f"&nbsp;&nbsp;&nbsp;<a href=\"{action_links.url(row['job_key'], 'Applied')}\">✓ Applied</a>"
            f" &nbsp;·&nbsp; <a href=\"{action_links.url(row['job_key'], 'Expired')}\">✗ Expired</a>"
            f" &nbsp;·&nbsp; <a href=\"{action_links.url(row['job_key'], 'Not eligible')}\">⏳ Needs experience</a>"
            f" &nbsp;·&nbsp; <a href=\"{action_links.url(row['job_key'], 'Scam')}\">⚑ Scam</a>")


def render(jobs: list[dict]) -> dict:
    """Summary + description for a morning event, from the jobs' CURRENT tracker rows.
    Open jobs whose fit has since dropped to Low (e.g. a PhD-only role) are left out."""
    from services.scam_check import company_key, scam_companies
    scam = scam_companies(jobs)
    jobs = [r for r in jobs if not is_open(r) or (_rank(r) < len(FITS_TO_REMIND) and company_key(r.get("company")) not in scam)]
    jobs = sorted(jobs, key=lambda r: (not is_open(r), _rank(r)))
    open_jobs = [r for r in jobs if is_open(r)]
    high = sum(1 for r in open_jobs if _rank(r) == 0)
    if open_jobs:
        summary = f"Apply to {len(open_jobs)} job{'s' * (len(open_jobs) != 1)} (GoForIt)"
        intro = f"{high} High, {len(open_jobs) - high} Medium fit. The job links open the posting; apply yourself."
    else:
        summary = "All done ✓ (GoForIt)"
        intro = "Every job here is marked Applied or Expired."
    hint = "✓ Applied / ✗ Expired / ⏳ Needs experience / ⚑ Scam update your tracker and this event (backend must be running on your laptop). ⚑ Scam also hides that company's future jobs."

    # Open the likely ones first: fresher-friendly titles, then the ones the alert says nothing about.
    fresher = [r for r in open_jobs if str(r.get("experience_signal")) == "Fresher-friendly"]
    unknown = [r for r in open_jobs if r not in fresher]
    done = [r for r in jobs if not is_open(r)]
    parts = []
    if fresher:
        parts.append("<b>Likely fresher-friendly</b>")
        parts += [_job_html(r) for r in fresher]
    if unknown:
        parts.append("<b>Experience not shown in the alert (check before applying)</b>" if fresher else
                     "<b>Experience not shown in the alert: check before applying</b>")
        parts += [_job_html(r) for r in unknown]
    if done:
        parts.append("<b>Done</b>")
        parts += [_job_html(r) for r in done]
    if fresher:
        intro += f" {len(fresher)} look fresher-friendly: start with those."
    return {"summary": summary,
            "description": f"{intro}<br><br>" + "<br><br>".join(parts) + f"<br><br><i>{hint}</i>"}


# ---------- creating and refreshing events ----------

def create_reminders(service, rows: list[dict], now: datetime | None = None, per_job: bool = False) -> dict[str, str]:
    """Creates/updates events. `rows` = ALL tracker rows. Returns {job_key: event_id} for newly reminded jobs."""
    now = now or datetime.now()
    from services.scam_check import company_key, scam_companies
    scam = scam_companies(rows)
    todo = sorted((r for r in rows if wants_reminder(r, now.date()) and company_key(r.get("company")) not in scam), key=_rank)
    done = {}
    if per_job:
        for row in todo:
            event = {**render([row]), "summary": f"Apply: {row['title']} @ {row['company']}", **_when(reminder_day(row, now))}
            done[row["job_key"]] = service.events().insert(calendarId="primary", body=event).execute()["id"]
        return done

    by_day: dict[date, list[dict]] = {}
    for row in todo:
        by_day.setdefault(reminder_day(row, now), []).append(row)
    for day, jobs in sorted(by_day.items()):
        marker = f"{DIGEST_KEY}={day.isoformat()}"
        existing = service.events().list(calendarId="primary", privateExtendedProperty=marker,
                                         singleEvents=True, maxResults=1).execute().get("items", [])
        if existing:
            event_id = existing[0]["id"]
            already = [r for r in rows if r.get("reminder_event") == event_id]
            service.events().patch(calendarId="primary", eventId=event_id, body=render(already + jobs)).execute()
        else:
            body = {**render(jobs), "extendedProperties": {"private": {DIGEST_KEY: day.isoformat()}}, **_when(day)}
            event_id = service.events().insert(calendarId="primary", body=body).execute()["id"]
        for row in jobs:
            done[row["job_key"]] = event_id
    return done


def refresh_recent_events(service, rows: list[dict], days: int = 14) -> int:
    """Re-renders events for recently received jobs (so fit changes show up). Returns how many."""
    since = (date.today() - timedelta(days=days)).isoformat()
    events = sorted({r["reminder_event"] for r in rows if r.get("reminder_event") and str(r.get("received")) >= since})
    for event_id in events:
        refresh_event(service, event_id, rows)
    return len(events)


def refresh_event(service, event_id: str, rows: list[dict]) -> None:
    """Re-renders one event from the tracker (after a ✓ Applied / ✗ Expired / ⚑ Scam click)."""
    from services.scam_check import company_key, scam_companies
    scam = scam_companies(rows)
    jobs = [r for r in rows if r.get("reminder_event") == event_id
            and not (is_open(r) and company_key(r.get("company")) in scam)]
    if not jobs:
        return
    body = render(jobs)
    if len(jobs) == 1 and is_open(jobs[0]):
        body["summary"] = f"Apply: {jobs[0]['title']} @ {jobs[0]['company']}"
    service.events().patch(calendarId="primary", eventId=event_id, body=body).execute()
