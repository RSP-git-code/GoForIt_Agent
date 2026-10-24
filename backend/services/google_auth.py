"""Google sign-in shared by the Gmail reader and the Calendar reminders.

Scopes (CLAUDE.md rule 8):
  - gmail.readonly   : read mail; can't send, delete, label or mark anything
  - calendar.events  : create/update the "apply" reminder events
credentials.json (OAuth Desktop-app client) and token.json (saved after you
sign in) live in config.GOFORIT_DIR, outside the repo.
"""

from pathlib import Path

from app import config

# Scheduled runs set this to False: if a fresh sign-in is needed, stop with a
# clear message instead of opening a browser nobody is watching.
INTERACTIVE = True


class SignInNeeded(Exception):
    pass


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def credentials():
    # Imported here so the rest of the backend works without Google's libraries.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    credentials_file: Path = config.GOFORIT_DIR / "credentials.json"
    token_file: Path = config.GOFORIT_DIR / "token.json"

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file))
        if not creds.has_scopes(SCOPES):
            creds = None  # signed in before a new permission was added: ask again once
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        from google.auth.exceptions import RefreshError
        try:
            creds.refresh(Request())
        except RefreshError:
            creds = None  # e.g. Google's 7-day limit for apps in "Testing": sign in again
    if not (creds and creds.valid):
        if not credentials_file.exists():
            raise FileNotFoundError(f"Put your Google OAuth Desktop-app file at {credentials_file}")
        if not INTERACTIVE:
            raise SignInNeeded("Google sign-in expired. Double-click check-jobs.bat once to sign in again.")
        # Opens your browser: sign in with the account that receives the alerts.
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        creds = flow.run_local_server(port=0, prompt="consent")
    token_file.write_text(creds.to_json(), encoding="utf8")
    return creds


def service(name: str, version: str):
    from googleapiclient.discovery import build

    return build(name, version, credentials=credentials(), cache_discovery=False)
