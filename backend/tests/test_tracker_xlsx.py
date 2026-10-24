"""The .xlsx tracker: no duplicates on re-run, your Status/Notes are never overwritten."""

from openpyxl import load_workbook

from services.tracker_xlsx import SHEET, load_rows, upsert

JOB_A = {"job_key": "linkedin:4012345678", "source": "LinkedIn", "received": "2026-10-05", "title": "Data Scientist",
         "company": "Acme", "location": "Hyderabad", "link": "https://www.linkedin.com/jobs/view/4012345678",
         "fit_score": 60, "matched_skills": ["Python", "SQL"]}
JOB_B = {"job_key": "indeed:abc123", "source": "Indeed", "received": "2026-10-05", "title": "ML Intern",
         "company": "Beta", "location": "Remote", "link": "https://in.indeed.com/viewjob?jk=abc123", "fit_score": 40,
         "matched_skills": []}


def test_create_and_no_duplicates(tmp_path):
    path = tmp_path / "GoForIt" / "applications.xlsx"
    first = upsert(path, [JOB_A, JOB_B])
    assert first == {"added": ["linkedin:4012345678", "indeed:abc123"], "updated": []}
    again = upsert(path, [JOB_A])
    assert again == {"added": [], "updated": ["linkedin:4012345678"]}
    rows = load_rows(path)
    assert len(rows) == 2
    assert rows["linkedin:4012345678"]["status"] == "New"
    assert rows["linkedin:4012345678"]["matched_skills"] == "Python, SQL"


def test_your_status_and_notes_are_kept(tmp_path):
    path = tmp_path / "applications.xlsx"
    upsert(path, [JOB_A])
    wb = load_workbook(path)
    ws = wb[SHEET]
    headers = [c.value for c in ws[1]]
    ws.cell(row=2, column=headers.index("Status") + 1, value="Applied")
    ws.cell(row=2, column=headers.index("Notes") + 1, value="Referral from senior")
    wb.save(path)

    upsert(path, [{**JOB_A, "fit_score": 75, "status": "New", "notes": ""}])
    row = load_rows(path)["linkedin:4012345678"]
    assert row["status"] == "Applied" and row["notes"] == "Referral from senior"
    assert row["fit_score"] == 75


def test_link_is_clickable(tmp_path):
    path = tmp_path / "applications.xlsx"
    upsert(path, [JOB_A])
    ws = load_workbook(path)[SHEET]
    headers = [c.value for c in ws[1]]
    assert ws.cell(row=2, column=headers.index("Link") + 1).hyperlink.target == JOB_A["link"]



def test_older_file_layout_is_rebuilt_without_losing_your_columns(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "applications.xlsx"
    old_headers = ["Job key", "Source", "Received", "Title", "Company", "Location", "Link", "Fit score",
                   "Matched skills", "Signals", "Reminder", "To Do task", "Status", "Notes"]
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(old_headers)
    ws.append(["linkedin:1", "LinkedIn", "2026-10-05", "AI Engineer", "Acme", "Pune", "https://x/1", "High (AI)",
               "AI", "", "2026-10-06 09:00", "", "Applied", "my note"])
    wb.save(path)

    upsert(path, [{**JOB_A, "job_key": "linkedin:2"}])
    rows = load_rows(path)
    old = rows["linkedin:1"]
    assert (old["title"], old["company"], old["fit_score"], old["status"], old["notes"]) == \
        ("AI Engineer", "Acme", "High (AI)", "Applied", "my note")
    assert [c.value for c in load_workbook(path)[SHEET][1]][:5] == ["Job key", "Source", "Received", "Posted", "Title"]


def test_status_dropdown_includes_new_statuses(tmp_path):
    path = tmp_path / "applications.xlsx"
    upsert(path, [JOB_A])
    upsert(path, [JOB_B])
    validations = load_workbook(path)[SHEET].data_validations.dataValidation
    assert len(validations) == 1 and "Scam" in validations[0].formula1 and "Expired" in validations[0].formula1
