"""Signed "✓ Applied / ✗ Expired" links for the calendar reminders.

Each link points to the local backend (127.0.0.1) and carries an HMAC
signature made with a random key stored in config.GOFORIT_DIR. Without the
key, a web page can't forge a link that changes your tracker. Only these two
statuses can be set this way.
"""

import hashlib
import hmac
import secrets
from urllib.parse import quote

from app import config

ALLOWED = ("Applied", "Expired", "Scam", "Not eligible")


def _key() -> bytes:
    path = config.GOFORIT_DIR / "action_key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf8")
    return bytes.fromhex(path.read_text(encoding="utf8").strip())


def sign(job_key: str, status: str) -> str:
    return hmac.new(_key(), f"{job_key}|{status}".encode(), hashlib.sha256).hexdigest()[:24]


def verify(job_key: str, status: str, sig: str) -> bool:
    return status in ALLOWED and hmac.compare_digest(sign(job_key, status), sig or "")


def url(job_key: str, status: str) -> str:
    return (f"http://{config.HOST}:{config.PORT}/inbox/mark?job={quote(job_key, safe='')}"
            f"&status={status}&sig={sign(job_key, status)}")
