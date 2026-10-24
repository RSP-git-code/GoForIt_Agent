"""Scam signals for job alerts, without ever opening a job page (rule 2).

1. Companies YOU marked as Scam in the tracker are remembered: their other
   and future jobs are rated Low and never reminded.
2. Red flags in the alert's own text (Indeed snippets): asking for a fee or
   deposit, moving the chat to WhatsApp/Telegram, "earn per day", "no interview".
   This is a warning, not a verdict.
"""

import re

from services.option_match import words

LEGAL_SUFFIX = re.compile(r"\b(private limited|pvt ltd|pvt|ltd|limited|llp|inc|corp|corporation|co|company|technologies|solutions)\b")

RED_FLAGS = [
    ("asks for a fee", re.compile(r"\b(registration|training|joining|processing|security|refundable|interview)\s+(fee|fees|charges?|deposit|amount)\b"
                                   r"|\b(pay|deposit)\s+(rs\.?|inr|₹)\s?\d", re.I)),
    ("contact via WhatsApp/Telegram", re.compile(r"\b(whats\s?app|telegram)\b", re.I)),
    ("too-good-to-be-true pay", re.compile(r"\bearn\s+(up to\s+)?(rs\.?|inr|₹)\s?[\d,]+\s*(per|/|a)\s*(day|hour)\b"
                                           r"|\b(no interview|without interview|instant joining|100% job guarantee|guaranteed job)\b", re.I)),
]


def company_key(name: str) -> str:
    """'Zetheta Algorithms Private Limited' and 'ZeTheta Algorithms' -> same key."""
    return " ".join(LEGAL_SUFFIX.sub(" ", words(name or "")).split())


def scam_companies(rows) -> set[str]:
    """Companies with at least one job you marked Scam."""
    return {company_key(r.get("company")) for r in rows if str(r.get("status")) == "Scam" and r.get("company")}


def red_flag(title: str, snippet: str) -> str:
    """The first red flag found in the alert text, or ""."""
    text = f"{title} {snippet}"
    return next((why for why, pattern in RED_FLAGS if pattern.search(text)), "")
