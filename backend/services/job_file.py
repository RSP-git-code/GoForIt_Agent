"""Text out of a job-description file the student uploads to Agent Octo (PDF or .txt).

Read here on the laptop with pdfplumber; the file and its text are never stored or logged.
Scanned PDFs (pictures of text) have no text layer, and there's no OCR, so they come back empty
and Octo asks the student to select or paste the text instead.
"""

import base64
import binascii
import io

import pdfplumber

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 15


class FileError(ValueError):
    """Something the student can fix (wrong type, too big, unreadable): the message says what."""


def read_job_file(name: str, data_base64: str) -> dict:
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise FileError("That file didn't come through properly. Try again?")
    if len(data) > MAX_BYTES:
        raise FileError("That file is over 10 MB. Job descriptions are usually much smaller.")
    lower = (name or "").lower()
    if lower.endswith(".txt"):
        return {"text": data.decode("utf-8", errors="replace").strip(), "pages": 1}
    if not (lower.endswith(".pdf") or data[:5] == b"%PDF-"):
        raise FileError("I can read PDF or .txt files.")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = pdf.pages[:MAX_PAGES]
            text = "\n".join((page.extract_text() or "") for page in pages)
            return {"text": text.strip(), "pages": len(pages)}
    except Exception:  # pdfminer raises many kinds of errors on damaged or locked PDFs
        raise FileError("I couldn't open that PDF (it may be damaged or password-protected).")
