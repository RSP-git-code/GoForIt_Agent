# GoForIt

A Chrome extension plus a local Python backend in which a team of orchestrated AI agents prefills job and campus-placement application forms for engineering students. **You always review and submit the form yourself. GoForIt never submits.**

Everything runs locally: our own fine-tuned field classifier and a small LLM served by Ollama, coordinated by a LangGraph pipeline. It uses no external LLM APIs.

> Status: early development. See the Progress section in [CLAUDE.md](CLAUDE.md).

## Setup

### Backend (Python 3.11)

```bash
cd backend
py -3.11 -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m app.main               # serves on http://127.0.0.1:8000
```

Check: open http://127.0.0.1:8000/health. It should return `{"status": "ok", ...}`.


### Extension

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the `extension/` folder.
4. Click the GoForIt icon. The popup shows whether the backend is online and how complete your profile is.
5. Click **Edit profile** to fill in your details. They are stored only in `chrome.storage.local`.

6. Open a form page and click **Fill this page**. Fields turn green (filled), yellow (review) or red (missing), and a summary panel appears. GoForIt never submits; you do.

To try it on the offline test forms, see [test-forms/README.md](test-forms/README.md).

### Tests

- Extension unit tests (Node 18+, no install): `node --test "extension/tests/*.test.js"`
- Fill all test forms in headless Chrome: `node extension/tests/run-harness.js`
- Backend: `pytest` from `backend/`

### Job alerts (LinkedIn/Indeed → Excel → Google Calendar)

- **Daily, automatic:** `install-daily-scan.ps1` registers a Windows task that runs at 8:30 AM (low priority, no window, ~10 s). Log: `Documents\GoForIt\inbox-log.txt`.
- **Now, by hand:** double-click `check-jobs.bat` (also used to sign in to Google again if the log says so).
- **Backend** for "Fill this page" and the ✓ Applied / ✗ Expired calendar links: double-click `start-backend.bat` and keep the window open.

## Architecture

_To be added (see CLAUDE.md §4 for now)._

## Metrics

See [docs/METRICS.md](docs/METRICS.md).

## Limitations

_To be added._
