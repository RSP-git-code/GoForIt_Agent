"""Google Calendar apply reminders, against a fake Calendar API (nothing real is created)."""

from datetime import datetime

from services.calendar_reminders import create_reminders, reminder_day, wants_reminder


class FakeCalendar:
    """Just enough of googleapiclient's events() API: insert, patch, list(privateExtendedProperty)."""

    def __init__(self):
        self.events_by_id = {}

    def events(self):
        return self

    def _call(self, result):
        return type("Call", (), {"execute": lambda _self: result})()

    def insert(self, calendarId, body):
        event_id = f"ev{len(self.events_by_id) + 1}"
        self.events_by_id[event_id] = {**body, "id": event_id}
        return self._call(self.events_by_id[event_id])

    def patch(self, calendarId, eventId, body):
        self.events_by_id[eventId].update(body)
        return self._call(self.events_by_id[eventId])

    def list(self, calendarId, privateExtendedProperty, singleEvents, maxResults):
        key, value = privateExtendedProperty.split("=")
        items = [e for e in self.events_by_id.values()
                 if e.get("extendedProperties", {}).get("private", {}).get(key) == value]
        return self._call({"items": items[:maxResults]})


NOW = datetime(2026, 10, 6, 8, 0)  # 8 AM on the 6th


def row(key, fit, received="2026-10-05", status="New", reminder_event=""):
    return {"job_key": key, "fit_score": fit, "received": received, "status": status, "reminder_event": reminder_event,
            "title": f"Job {key}", "company": "Acme", "location": "Hyderabad", "link": f"https://example.com/{key}"}


def test_only_new_high_and_medium_jobs_are_reminded():
    assert wants_reminder(row("a", "High (AI, ML)"))
    assert wants_reminder(row("b", "Medium (AI)"))
    assert not wants_reminder(row("c", "Low (senior role)"))
    assert not wants_reminder(row("d", "High (AI)", status="Applied"))
    assert not wants_reminder(row("e", "High (AI)", reminder_event="ev9"))  # already reminded


def test_reminder_day_is_next_morning_or_the_next_upcoming_one():
    assert str(reminder_day(row("a", "High", received="2026-10-05"), NOW)) == "2026-10-06"  # still before 9 AM
    assert str(reminder_day(row("a", "High", received="2026-10-01"), NOW)) == "2026-10-06"  # old alert: next 9 AM
    after_nine = datetime(2026, 10, 6, 10, 0)
    assert str(reminder_day(row("a", "High", received="2026-10-05"), after_nine)) == "2026-10-07"


def test_one_morning_event_lists_jobs_best_first_and_later_runs_add_to_it():
    cal = FakeCalendar()
    first = create_reminders(cal, [row("m", "Medium (AI)"), row("h", "High (AI, ML)"), row("l", "Low")], now=NOW)
    assert set(first) == {"m", "h"} and len(cal.events_by_id) == 1
    event = cal.events_by_id["ev1"]
    assert event["summary"] == "Apply to 2 jobs (GoForIt)"
    assert event["start"]["dateTime"] == "2026-10-06T09:00:00" and event["start"]["timeZone"] == "Asia/Kolkata"
    assert event["reminders"]["overrides"] == [{"method": "popup", "minutes": 0}]
    assert event["description"].index("Job h") < event["description"].index("Job m")  # High first
    assert "https://example.com/h" in event["description"]

    reminded = [row("m", "Medium (AI)", reminder_event="ev1"), row("h", "High (AI, ML)", reminder_event="ev1")]
    second = create_reminders(cal, reminded + [row("x", "High (Python)")], now=NOW)  # same morning
    assert second == {"x": "ev1"} and len(cal.events_by_id) == 1
    assert cal.events_by_id["ev1"]["summary"] == "Apply to 3 jobs (GoForIt)"


def test_per_job_events():
    cal = FakeCalendar()
    done = create_reminders(cal, [row("a", "High (AI)"), row("b", "Medium (AI)")], now=NOW, per_job=True)
    assert len(done) == 2 and len(cal.events_by_id) == 2
    assert cal.events_by_id[done["a"]]["summary"] == "Apply: Job a @ Acme"


def test_old_postings_are_treated_as_probably_expired():
    from datetime import date
    fresh = {**row("f", "High (AI)"), "posted": "2026-10-04"}
    stale = {**row("s", "High (AI)"), "posted": "2026-09-01"}
    assert wants_reminder(fresh, date(2026, 10, 6)) and not wants_reminder(stale, date(2026, 10, 6))
    cal = FakeCalendar()
    assert set(create_reminders(cal, [fresh, stale], now=NOW)) == {"f"}
    assert not wants_reminder({**row("e", "High (AI)"), "status": "Expired"})


def test_each_job_has_signed_applied_and_expired_links(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "GOFORIT_DIR", tmp_path)
    cal = FakeCalendar()
    create_reminders(cal, [row("linkedin:1", "High (AI)")], now=NOW)
    html = cal.events_by_id["ev1"]["description"]
    assert "/inbox/mark?job=linkedin%3A1&amp;status=Applied&amp;sig=" in html or "/inbox/mark?job=linkedin%3A1&status=Applied&sig=" in html
    assert "✗ Expired" in html and "https://example.com/linkedin:1" in html


def test_jobs_that_drop_to_low_leave_the_event():
    from services.calendar_reminders import refresh_event
    cal = FakeCalendar()
    create_reminders(cal, [row("a", "High (AI)"), row("b", "Medium (AI)")], now=NOW)
    rows = [row("a", "High (AI)", reminder_event="ev1"), row("b", "Low (for PhD students)", reminder_event="ev1")]
    refresh_event(cal, "ev1", rows)
    assert cal.events_by_id["ev1"]["summary"] == "Apply to 1 job (GoForIt)"
    assert "Job b" not in cal.events_by_id["ev1"]["description"]


def test_fresher_friendly_jobs_come_first_in_the_event():
    cal = FakeCalendar()
    rows = [{**row("a", "High (AI)"), "title": "AI Engineer", "experience_signal": "Not stated: check"},
            {**row("b", "Medium (AI)"), "title": "AI Intern", "experience_signal": "Fresher-friendly"}]
    create_reminders(cal, rows, now=NOW)
    html = cal.events_by_id["ev1"]["description"]
    assert html.index("Likely fresher-friendly") < html.index("AI Intern") < html.index("Experience not shown") < html.index("AI Engineer")
    assert "1 look fresher-friendly" in html
