"""GET /inbox/mark: the "✓ Applied / ✗ Expired" links in the calendar reminders.

Checks the link's signature, sets the job's Status in the tracker, and
re-renders its calendar event. Answers with a tiny HTML page you can close.
"""

from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app import config
from services import action_links, calendar_reminders, tracker_xlsx

router = APIRouter()


def _page(message: str, ok: bool = True) -> HTMLResponse:
    color = "#1a7f37" if ok else "#cf222e"
    html = (f"<!doctype html><meta charset='utf-8'><title>GoForIt</title>"
            f"<body style='font-family:system-ui;max-width:520px;margin:60px auto'>"
            f"<h2 style='color:{color}'>{escape(message)}</h2><p>You can close this tab.</p></body>")
    return HTMLResponse(html, status_code=200 if ok else 400)


# Swapped out in tests so no real Google call is made.
def calendar_service():
    from services import google_auth
    return google_auth.service("calendar", "v3")


@router.get("/inbox/mark", response_class=HTMLResponse)
def mark(job: str, status: str, sig: str):
    if not action_links.verify(job, status, sig):
        return _page("This link isn't valid (it wasn't made by GoForIt on this laptop).", ok=False)
    rows = tracker_xlsx.load_rows(config.TRACKER_PATH)
    row = rows.get(job)
    if not row:
        return _page("That job isn't in your tracker any more.", ok=False)
    try:
        tracker_xlsx.upsert(config.TRACKER_PATH, [{"job_key": job, "status": status}], user_columns_ok=True)
    except PermissionError:
        return _page("Your tracker is open in Excel. Close it and click the link again.", ok=False)

    event_id = row.get("reminder_event")
    if event_id:
        try:
            calendar_reminders.refresh_event(calendar_service(), event_id,
                                             list(tracker_xlsx.load_rows(config.TRACKER_PATH).values()))
        except Exception:
            return _page(f"Marked {row['title']} @ {row['company']} as {status} in your tracker, "
                         f"but couldn't update the calendar event (check your internet).", ok=True)
    return _page(f"Marked {row['title']} @ {row['company']} as {status}.")
