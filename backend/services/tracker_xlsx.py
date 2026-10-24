"""The applications tracker: a local .xlsx file, one row per job.

- Rows are keyed by `job_key` ("linkedin:4012345678", "indeed:abc123"), so
  running the Inbox agent again updates rows instead of duplicating them.
- Columns you edit yourself (Status, Notes) are never overwritten.
- The file lives outside the repo (config.TRACKER_PATH); it holds job
  listings, not profile data.
"""

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

SHEET = "Applications"
STATUSES = ["New", "Applying", "Applied", "Interview", "Offer", "Rejected", "Skipped", "Expired", "Scam", "Not eligible"]

# (header, row key, column width). Order = column order in the sheet.
COLUMNS = [
    ("Job key", "job_key", 22),
    ("Source", "source", 10),
    ("Received", "received", 12),
    ("Posted", "posted", 12),
    ("Title", "title", 36),
    ("Company", "company", 24),
    ("Location", "location", 22),
    ("Link", "link", 40),
    ("Fit", "fit_score", 22),
    ("Matched skills", "matched_skills", 30),
    ("Experience", "experience_signal", 18),
    ("Signals", "notes_hint", 28),
    ("Reminder", "reminder", 18),
    ("Reminder event", "reminder_event", 16),
    ("Status", "status", 12),
    ("Notes", "notes", 30),
]
USER_COLUMNS = {"status", "notes"}  # yours: never overwritten by GoForIt
HEADERS = [c[0] for c in COLUMNS]
KEYS = [c[1] for c in COLUMNS]


def _new_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADERS)
    for i, (_, _, width) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
        cell = ws.cell(row=1, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F6FEB")
    ws.freeze_panes = "A2"  # header stays visible while scrolling
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(COLUMNS)).column_letter}1"
    # Status column gets a dropdown.
    _status_dropdown(ws)
    return wb


def _status_dropdown(ws) -> None:
    """(Re)creates the Status dropdown, so older files get new statuses like "Scam"."""
    ws.data_validations.dataValidation = []
    status_col = ws.cell(row=1, column=KEYS.index("status") + 1).column_letter
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{status_col}2:{status_col}5000")


def _cell_value(key: str, value):
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value if value is not None else ""


# Older header names, so files made by earlier versions still read correctly.
OLD_HEADERS = {"Fit score": "fit_score", "To Do task": "reminder_event"}


def _read_sheet(ws) -> list[dict]:
    """Rows as dicts, matched by HEADER NAME (not position), so added columns don't shift data."""
    names = {**OLD_HEADERS, **{h: k for h, k, _ in COLUMNS}}
    header_keys = [names.get(str(c.value or "").strip()) for c in ws[1]]
    rows = []
    for values in ws.iter_rows(min_row=2, values_only=True):
        row = {k: "" for k in KEYS}
        for key, value in zip(header_keys, values):
            if key:
                row[key] = value if value is not None else ""
        if row.get("job_key"):
            rows.append(row)
    return rows


def load_rows(path: Path) -> dict[str, dict]:
    """job_key -> row dict, for whatever is already in the sheet."""
    if not path.exists():
        return {}
    return {r["job_key"]: r for r in _read_sheet(load_workbook(path)[SHEET])}


def _workbook_for(path: Path):
    """The existing workbook, rebuilt in the current column layout if it's from an older version."""
    if not path.exists():
        return _new_workbook()
    wb = load_workbook(path)
    if [c.value for c in wb[SHEET][1]][: len(HEADERS)] == HEADERS:
        return wb
    old_rows = _read_sheet(wb[SHEET])
    wb = _new_workbook()
    for row in old_rows:
        wb[SHEET].append([_cell_value(k, row[k]) for k in KEYS])
    return wb


def upsert(path: Path, new_rows: list[dict], user_columns_ok: bool = False) -> dict:
    """Adds new jobs and updates known ones. Returns {"added": [...], "updated": [...]} job keys.

    Status/Notes are yours: only written when `user_columns_ok` (you clicked
    "✓ Applied" / "✗ Expired" in a reminder)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = _workbook_for(path)
    ws = wb[SHEET]
    _status_dropdown(ws)
    where = {ws.cell(row=r, column=1).value: r for r in range(2, ws.max_row + 1) if ws.cell(row=r, column=1).value}
    added, updated = [], []
    for row in new_rows:
        key = row["job_key"]
        if key in where:
            r = where[key]
            for col, k in enumerate(KEYS, start=1):
                if (k in USER_COLUMNS and not user_columns_ok) or k not in row:
                    continue  # never touch your Status/Notes; keep columns the update doesn't mention
                ws.cell(row=r, column=col, value=_cell_value(k, row[k]))
            updated.append(key)
        else:
            values = {**{k: "" for k in KEYS}, "status": "New", **row}
            ws.append([_cell_value(k, values[k]) for k in KEYS])
            r = ws.max_row
            where[key] = r
            added.append(key)
        link_cell = ws.cell(row=where[key], column=KEYS.index("link") + 1)
        if link_cell.value:
            link_cell.hyperlink = link_cell.value  # clickable in Excel (you open it, GoForIt never does)
            link_cell.font = Font(color="0563C1", underline="single")

    wb.save(path)
    return {"added": added, "updated": updated}
