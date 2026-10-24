"""Backend settings. The host is fixed to localhost: profile data must never leave the machine."""

HOST = "127.0.0.1"
PORT = 8000
VERSION = "0.0.1"

# Local LLM (Ollama, on this laptop only). "ollama": the Drafter writes free-text
# answers and the Verifier also asks the model to check them. "stub": template
# drafts and rule checks only (tests). Override with GOFORIT_LLM / GOFORIT_DRAFT_MODEL.
import os as _os
OLLAMA_URL = "http://127.0.0.1:11434"
LLM_BACKEND = _os.environ.get("GOFORIT_LLM", "stub")  # "ollama" once the panel shows drafts as they arrive
# Qwen3 1.7B: 3-4x faster than Llama 3.2 3B on this laptop, honest on trap questions, no worse at
# inventing details (docs/METRICS.md, 2026-10-18).
DRAFT_MODEL = _os.environ.get("GOFORIT_DRAFT_MODEL", "qwen3:1.7b")
# The Verifier's judge: a different model from the writer, so it doesn't just agree with itself.
# Qwen3 1.7B caught 18/18 planted lies with 0/10 honest answers rejected (docs/METRICS.md).
JUDGE_MODEL = _os.environ.get("GOFORIT_JUDGE_MODEL", "qwen3:1.7b")
LLM_TIMEOUT = 180  # seconds per model call on the laptop CPU

# Drafter <-> Verifier loop: how many times a rejected draft is rewritten.
MAX_DRAFT_RETRIES = 2

# Applications tracker (.xlsx). Lives in your Windows Documents folder, outside
# the repo. Override with the GOFORIT_TRACKER environment variable.
import os
from pathlib import Path


def _documents_dir() -> Path:
    """The real Windows Documents folder (OneDrive can move it), else ~/Documents."""
    if os.name == "nt":
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:  # 5 = My Documents
            return Path(buf.value)
    return Path.home() / "Documents"


# Your GoForIt folder: tracker, Google credentials/token, exported profile. Outside the repo.
GOFORIT_DIR = Path(os.environ.get("GOFORIT_DIR") or _documents_dir() / "GoForIt")
TRACKER_PATH = Path(os.environ.get("GOFORIT_TRACKER") or GOFORIT_DIR / "applications.xlsx")

# Job alerts have no deadline: remind me the next morning at this hour (Google Calendar).
REMINDER_HOUR = 9
TIMEZONE = "Asia/Kolkata"

# Jobs posted longer ago than this are "probably expired": no reminder.
# (We can't check a job page: opening job-board pages is off-limits, rule 2.)
MAX_JOB_AGE_DAYS = 21
