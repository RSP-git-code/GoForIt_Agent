"""Inbox command: job alerts -> Excel tracker.

Run from the backend/ folder:
    python -m app.inbox                 # read LinkedIn/Indeed alerts from Gmail (last 14 days)
    python -m app.inbox --days 30
    python -m app.inbox --folder PATH   # use downloaded .eml files instead of Gmail
    python -m app.inbox --no-reminders  # only update the Excel tracker
    python -m app.inbox --per-job       # one calendar event per job instead of one per morning
    python -m app.inbox --scheduled     # for the daily Windows task: no browser, output to a log file
    python -m app.inbox --refresh       # only re-render GoForIt calendar events from the Excel
                                        # (adds ✓ Applied / ✗ Expired links, shows Status you changed in Excel)

High/Medium-fit jobs still marked "New" get a Google Calendar reminder at
9 AM (once per job; see services/calendar_reminders.py).

The profile is read from a JSON export of your GoForIt profile (Edit profile ->
Export JSON), looked for in Documents\\GoForIt\\ first. Prints only counts and
job titles, never email contents.
"""

import argparse
import json
import sys
from pathlib import Path

from agents.inbox import process_alerts
from app import config
from services.tracker_xlsx import load_rows, upsert

PROFILE_NAMES = ["profile.json", "goforit-profile.json"]


def find_profile(explicit: str | None) -> Path | None:
    candidates = [Path(explicit)] if explicit else [config.GOFORIT_DIR / n for n in PROFILE_NAMES] + \
        [Path(__file__).resolve().parents[2] / "profile.json"]
    return next((p for p in candidates if p.exists()), None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LinkedIn/Indeed job alerts -> Excel tracker")
    parser.add_argument("--days", type=int, default=14, help="how many days of alerts to read from Gmail")
    parser.add_argument("--folder", help="read .eml files from this folder instead of Gmail")
    parser.add_argument("--profile", help="path to your exported GoForIt profile JSON")
    parser.add_argument("--no-reminders", action="store_true", help="don't create Google Calendar reminders")
    parser.add_argument("--per-job", action="store_true", help="one calendar event per job instead of one per morning")
    parser.add_argument("--refresh", action="store_true", help="only re-render calendar events from the Excel tracker")
    parser.add_argument("--scheduled", action="store_true", help="daily task mode: log to a file, never open a browser")
    parser.add_argument("--logged", action="store_true", help="show output AND save it to the log (check-jobs.bat)")
    args = parser.parse_args(argv)

    if args.scheduled or args.logged:
        return _run(argv, scheduled=args.scheduled)

    if args.refresh:
        from services import google_auth
        from services.calendar_reminders import refresh_event
        rows = list(load_rows(config.TRACKER_PATH).values())
        events = sorted({r["reminder_event"] for r in rows if r.get("reminder_event")})
        service = google_auth.service("calendar", "v3")
        for event_id in events:
            refresh_event(service, event_id, rows)
        print(f"Calendar: refreshed {len(events)} GoForIt event(s) from {config.TRACKER_PATH.name}.")
        return 0

    profile_path = find_profile(args.profile)
    if not profile_path:
        print(f"No profile found. In GoForIt: Edit profile -> Export JSON, and save it in {config.GOFORIT_DIR}")
        return 2
    profile = json.loads(profile_path.read_text(encoding="utf8"))

    if args.folder:
        from services.gmail_reader import read_folder
        mails = read_folder(Path(args.folder))
        where = f"{len(mails)} .eml files in {args.folder}"
    else:
        from services.gmail_reader import fetch_alerts
        mails = fetch_alerts(days=args.days)
        where = f"{len(mails)} alert emails from Gmail (last {args.days} days)"

    from services.scam_check import scam_companies
    known = load_rows(config.TRACKER_PATH) if config.TRACKER_PATH.exists() else {}
    from agents.inbox import companies_needing_experience
    rows = process_alerts(mails, profile, scam_companies(known.values()), companies_needing_experience(known.values()))
    try:
        result = upsert(config.TRACKER_PATH, rows)
    except PermissionError:
        # Windows locks a workbook while Excel has it open.
        print(f"Found {len(rows)} jobs, but {config.TRACKER_PATH.name} is open in Excel. Close it and run this again.")
        return 1
    print(f"Read {where} -> {len(rows)} jobs. Added {len(result['added'])}, updated {len(result['updated'])}.")
    print(f"Tracker: {config.TRACKER_PATH}")
    new = [r for r in rows if r["job_key"] in set(result["added"])]
    for r in sorted(new, key=lambda r: ("High", "Medium", "Low").index(r["fit_score"].split()[0])):
        print(f"  {r['fit_score'][:30]:31} {r['title'][:50]:51} {r['company'][:30]}")

    if not args.no_reminders:
        from services import google_auth
        from services.calendar_reminders import create_reminders, probably_expired, refresh_recent_events
        all_rows = list(load_rows(config.TRACKER_PATH).values())
        old = [r for r in all_rows if str(r.get("status") or "New") == "New" and probably_expired(r)]
        if old:
            print(f"Skipping {len(old)} job(s) posted over {config.MAX_JOB_AGE_DAYS} days ago (probably expired).")
        calendar = google_auth.service("calendar", "v3")
        refresh_recent_events(calendar, all_rows)  # fit changes (e.g. now "Low (for PhD students)") show up
        done = create_reminders(calendar, all_rows, per_job=args.per_job)
        if done:
            upsert(config.TRACKER_PATH, [{"job_key": k, "reminder_event": v} for k, v in done.items()])
        print(f"Calendar: {len(done)} High/Medium job(s) added to 9 AM apply reminders." if done
              else "Calendar: no new High/Medium jobs to remind you about.")
    return 0


def _append_log(text: str, label: str, code: int) -> None:
    """Appends one run's output to Documents\\GoForIt\\inbox-log.txt (last ~200 lines kept)."""
    from datetime import datetime

    log = config.GOFORIT_DIR / "inbox-log.txt"
    log.parent.mkdir(parents=True, exist_ok=True)
    old = log.read_text(encoding="utf8").splitlines()[-200:] if log.exists() else []
    stamp = f"--- {datetime.now():%Y-%m-%d %H:%M} ({label}, exit {code}) ---"
    log.write_text("\n".join(old + [stamp] + text.splitlines()) + "\n", encoding="utf8")


class _Tee:
    """Writes to the console AND keeps a copy (for the log)."""

    def __init__(self, console):
        import io
        self.console, self.copy = console, io.StringIO()

    def write(self, text):
        self.console.write(text)
        self.copy.write(text)

    def flush(self):
        self.console.flush()


def _run(argv, scheduled: bool) -> int:
    """One run with its output saved to the log. Scheduled runs show nothing and never open a browser."""
    import contextlib
    import io

    from services import google_auth

    args = [a for a in (argv if argv is not None else sys.argv[1:]) if a not in ("--scheduled", "--logged")]
    google_auth.INTERACTIVE = not scheduled
    out = io.StringIO() if scheduled else _Tee(sys.stdout)
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(args)
        except google_auth.SignInNeeded as err:
            print(err)
            code = 3
        except Exception as err:  # network down, Google hiccup: try again next time
            print(f"Run failed: {type(err).__name__}: {err}")
            code = 1
    text = out.getvalue() if scheduled else out.copy.getvalue()
    _append_log(text, "daily scan" if scheduled else "check-jobs", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
