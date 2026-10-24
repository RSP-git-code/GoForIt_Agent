"""Reads LinkedIn and Indeed job-alert emails from Gmail, read-only (CLAUDE.md rule 8).

- Scope is gmail.readonly: it can't send, delete, label or mark anything.
- The search only matches the two alert senders, so no other mail is ever fetched.
- Sign-in is shared with the Calendar reminders (services/google_auth.py).
- Nothing from the emails is logged.
"""

import base64
from pathlib import Path

from services import google_auth
from services.alert_parser import read_eml

ALERT_QUERY = "from:(jobalerts-noreply@linkedin.com OR donotreply@jobalert.indeed.com)"


def fetch_alerts(days: int = 14, max_messages: int = 200) -> list[dict]:
    """Job-alert emails from the last `days` days, as {id, from, subject, date, body}."""
    service = google_auth.service("gmail", "v1")
    messages, page = [], None
    while len(messages) < max_messages:
        resp = service.users().messages().list(
            userId="me", q=f"{ALERT_QUERY} newer_than:{days}d", maxResults=min(100, max_messages), pageToken=page
        ).execute()
        messages += resp.get("messages", [])
        page = resp.get("nextPageToken")
        if not page:
            break

    mails = []
    for m in messages[:max_messages]:
        raw = service.users().messages().get(userId="me", id=m["id"], format="raw").execute()["raw"]
        mail = read_eml(base64.urlsafe_b64decode(raw))
        mail["id"] = m["id"]
        mails.append(mail)
    return mails


def read_folder(folder: Path) -> list[dict]:
    """Same output from downloaded .eml files (no Google sign-in needed)."""
    return [read_eml(p.read_bytes()) for p in sorted(Path(folder).glob("*.eml"))]
