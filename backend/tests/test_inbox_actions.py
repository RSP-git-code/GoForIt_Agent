"""Clicking ✓ Applied / ✗ Expired in a reminder updates the tracker and the event."""

from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routes import inbox_actions
from services import action_links, calendar_reminders
from services.tracker_xlsx import load_rows, upsert
from tests.test_calendar_reminders import NOW, FakeCalendar, row

client = TestClient(app)


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GOFORIT_DIR", tmp_path)
    monkeypatch.setattr(config, "TRACKER_PATH", tmp_path / "applications.xlsx")
    cal = FakeCalendar()
    monkeypatch.setattr(inbox_actions, "calendar_service", lambda: cal)
    jobs = [row("linkedin:1", "High (AI)"), row("indeed:2", "Medium (AI)")]
    upsert(config.TRACKER_PATH, jobs)
    done = calendar_reminders.create_reminders(cal, jobs, now=NOW)
    upsert(config.TRACKER_PATH, [{"job_key": k, "reminder_event": v} for k, v in done.items()])
    return cal


def click(job, status, sig=None):
    return client.get("/inbox/mark", params={"job": job, "status": status, "sig": sig or action_links.sign(job, status)})


def test_expired_click_updates_tracker_and_event(tmp_path, monkeypatch):
    cal = setup(tmp_path, monkeypatch)
    resp = click("indeed:2", "Expired")
    assert resp.status_code == 200 and "Expired" in resp.text
    assert load_rows(config.TRACKER_PATH)["indeed:2"]["status"] == "Expired"
    event = cal.events_by_id["ev1"]
    assert event["summary"] == "Apply to 1 job (GoForIt)"
    assert "<s>Job indeed:2 @ Acme</s> (Expired)" in event["description"]

    click("linkedin:1", "Applied")
    assert cal.events_by_id["ev1"]["summary"] == "All done ✓ (GoForIt)"


def test_forged_or_unknown_links_change_nothing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    assert click("indeed:2", "Expired", sig="0" * 24).status_code == 400
    assert click("indeed:2", "Rejected").status_code == 400  # only Applied / Expired via links
    assert load_rows(config.TRACKER_PATH)["indeed:2"]["status"] == "New"


def test_needs_experience_link(tmp_path, monkeypatch):
    cal = setup(tmp_path, monkeypatch)
    assert click("indeed:2", "Not eligible").status_code == 200
    assert load_rows(config.TRACKER_PATH)["indeed:2"]["status"] == "Not eligible"
    assert "⏳ <s>Job indeed:2 @ Acme</s> (Not eligible)" in cal.events_by_id["ev1"]["description"]
