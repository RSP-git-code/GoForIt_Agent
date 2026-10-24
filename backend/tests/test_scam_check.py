"""Scam signals: your own Scam marks are remembered; red flags in alert text."""

from agents.inbox import process_alerts
from services.alert_parser import read_eml
from services.calendar_reminders import create_reminders, refresh_event
from services.scam_check import company_key, red_flag, scam_companies
from tests.test_alerts import FIXTURE, PROFILE
from tests.test_calendar_reminders import NOW, FakeCalendar, row


def test_company_names_are_compared_without_legal_suffixes():
    assert company_key("Zetheta Algorithms Private Limited") == company_key("ZeTheta Algorithms") == "zetheta algorithms"
    assert company_key("Innova ESI Pvt. Ltd.") == "innova esi"


def test_companies_you_marked_scam_are_remembered():
    rows = [{"company": "Innova ESI", "status": "Scam"}, {"company": "Acme", "status": "Applied"}]
    scam = scam_companies(rows)
    assert scam == {"innova esi"}
    jobs = process_alerts([read_eml(FIXTURE.read_bytes())], PROFILE, scam)
    innova = [j for j in jobs if j["company"] == "Innova ESI"]
    assert innova and all(j["fit_score"] == "Low (company you marked as scam)" for j in innova)


def test_red_flags_in_alert_text():
    assert red_flag("Data Entry Intern", "Pay a refundable security deposit of Rs 2000 to start") == "asks for a fee"
    assert red_flag("Online Work", "Earn ₹3,000 per day from home. Contact us on WhatsApp") == "contact via WhatsApp/Telegram"
    assert red_flag("Process Associate", "Instant joining, no interview!") == "too-good-to-be-true pay"
    assert red_flag("ML Engineer", "Build models with Python and SQL; training provided") == ""


def test_scam_companies_get_no_reminder_and_leave_events():
    cal = FakeCalendar()
    rows = [row("a", "High (AI)"), {**row("b", "High (AI)"), "company": "Scammy Co"},
            {**row("c", "Low"), "company": "Scammy Co", "status": "Scam"}]
    assert set(create_reminders(cal, rows, now=NOW)) == {"a"}

    cal2 = FakeCalendar()
    create_reminders(cal2, [row("a", "High (AI)"), {**row("b", "Medium (AI)"), "company": "Scammy Co"}], now=NOW)
    later = [row("a", "High (AI)", reminder_event="ev1"),
             {**row("b", "Medium (AI)", reminder_event="ev1"), "company": "Scammy Co", "status": "Scam"}]
    refresh_event(cal2, "ev1", later)
    assert cal2.events_by_id["ev1"]["summary"] == "Apply to 1 job (GoForIt)"
    assert "⚑ <s>Job b @ Scammy Co</s> (Scam)" in cal2.events_by_id["ev1"]["description"]
