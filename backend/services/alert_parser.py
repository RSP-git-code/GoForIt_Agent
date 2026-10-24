"""Splits LinkedIn and Indeed job-alert emails into one record per job.

LinkedIn's plain-text alert (checked against a real one, 2026-10-05) is a list
of blocks separated by "-----" lines:

    Python + AI Engineer          <- title
    Innova ESI                    <- company
    Bengaluru                     <- location
    This company is actively hiring        <- optional signals
    Apply with resume & profile
    View job: https://www.linkedin.com/comm/jobs/view/4475544144/?trackingId=...&otpToken=...

SECURITY: alert links carry tracking IDs and an `otpToken` (a one-time sign-in
token). We never keep them: only the clean job URL is stored. Footer blocks
(which include the recipient's name and headline) are ignored.

Indeed's plain-text alert (checked against a real one, 2026-10-06) is one
paragraph per job:

    AIML Engineer Digital & AI                      <- title
    IQ-EQ - Gachibowli, Hyderabad, Telangana        <- "Company - Location"
    ₹50,000 - ₹80,000 a month / Easily apply / Responsive employer   <- optional
    You will work with cross-functional teams ...   <- snippet
    Just posted / 2 days ago
    https://in.indeed.com/rc/clk/dl?jk=b2a0947f0af15aa3&...           <- personalised link

Sponsored jobs link via /pagead/ with no job ID. Indeed marks these links
"personalised to you", so we never store them: jobs with a jk get
in.indeed.com/viewjob?jk=..., sponsored ones get a plain Indeed search link.
"""

import hashlib
from urllib.parse import quote_plus

import email
import re
from datetime import datetime, timezone
from email import policy
from email.utils import parsedate_to_datetime
from html import unescape

LINKEDIN_JOB = re.compile(r"https?://(?:[\w-]+\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)")
INDEED_JOB = re.compile(r"https?://(?:[\w-]+\.)?indeed\.(?:com|co\.in)/\S*?[?&]jk=([0-9a-f]+)\S*", re.I)  # \S* eats the rest of the link (tokens)
SIGNAL_LINES = re.compile(
    r"actively hiring|apply with resume|easy apply|early applicant|connections?\b|alumni|promoted|be among|"
    r"applicants?\b|reposted|new\b|^\d+ (?:day|week|hour|minute)s? ago|responds? within|urgently hiring|"
    r"^₹|salary|\bper (?:month|year|annum)\b|\ba (?:month|year)\b|lpa\b", re.I)


# ---------- reading an email ----------

def read_eml(raw: bytes) -> dict:
    """A downloaded .eml (or Gmail's raw message) -> {id, from, subject, date, body}."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    part = msg.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    if part is not None and part.get_content_type() == "text/html":
        body = html_to_text(body)
    try:
        received = parsedate_to_datetime(msg["Date"]).astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        received = datetime.now(timezone.utc).date().isoformat()
    return {"id": msg["Message-ID"] or "", "from": str(msg["From"] or ""), "subject": str(msg["Subject"] or ""),
            "date": received, "body": body.replace("\r\n", "\n")}


def html_to_text(html: str) -> str:
    """Crude HTML -> text that keeps links: <a href="X">Y</a> becomes "Y X"."""
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r'(?is)<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"{m.group(2)} {m.group(1)}\n", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return "\n".join(line.strip() for line in text.splitlines())


# ---------- which alert is it? ----------

def source_of(sender: str) -> str | None:
    s = (sender or "").lower()
    if "linkedin.com" in s:
        return "LinkedIn"
    if re.search(r"indeed\.(com|co\.in)", s):
        return "Indeed"
    return None


# ---------- parsing ----------

def _clean_lines(block: str) -> list[str]:
    return [line.strip() for line in block.splitlines() if line.strip()]


def _record(source: str, job_id: str, link: str, info: list[str], received: str, query: str, snippet: str = "") -> dict:
    signals = [l for l in info if SIGNAL_LINES.search(l)]
    core = [l for l in info if l not in signals]
    # Some LinkedIn alerts add a description line after title/company/location.
    if not snippet and len(core) > 3:
        snippet = " ".join(core[3:])
    return {
        "snippet": snippet,
        "job_key": f"{source.lower()}:{job_id}",
        "source": source,
        "received": received,
        "title": core[0] if len(core) > 0 else "",
        "company": core[1] if len(core) > 1 else "",
        "location": core[2] if len(core) > 2 else "",
        "link": link,
        "signals": signals,
        "alert_query": query,
    }


def parse_linkedin(body: str, received: str) -> list[dict]:
    m = re.search(r"your job alert for (.+?)\s*$", body, re.I | re.M)
    query = m.group(1).strip() if m else ""
    jobs, seen = [], set()
    for block in re.split(r"\n-{10,}[ \t]*\n", body):
        found = LINKEDIN_JOB.search(block)
        if not found or found.group(1) in seen:
            continue
        seen.add(found.group(1))
        before = block[: found.start()]
        info = [l for l in _clean_lines(before)
                if not re.match(r"(?i)your job alert for|view job:?$", l) and not l.lower().startswith("view job")]
        link = f"https://www.linkedin.com/jobs/view/{found.group(1)}/"  # tokens and tracking dropped
        jobs.append(_record("LinkedIn", found.group(1), link, info, received, query))
    return jobs


# Only job links (not Privacy / Terms / Help / Manage alerts in the footer).
INDEED_LINK = re.compile(r"https?://(?:[\w-]+\.)?indeed\.(?:com|co\.in)/(?:rc/clk|pagead/clk|viewjob)\S*", re.I)
INDEED_SIGNAL = re.compile(r"^(easily apply|responsive employer|urgently hiring|just posted|today|new|hiring multiple candidates|"
                           r"\d+\+? (?:day|days|hour|hours) ago|active \d+ days? ago)$|₹|\$|\ba (?:month|year|week|day)$", re.I)


def parse_indeed(body: str, received: str) -> list[dict]:
    m = re.search(r"\d+ new (.+?) (?:vacancies|jobs)", body, re.I)
    query = m.group(1).strip() if m else ""
    jobs, seen = [], set()
    for block in re.split(r"\n[ \t]*\n", body):
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        url_at = next((i for i, l in enumerate(lines) if INDEED_LINK.search(l)), None)
        if url_at is None or url_at < 2:
            continue  # headers, footers, "See matching results on Indeed: <link>"
        text = lines[:url_at]
        title, company_line, rest = text[0], text[1], text[2:]
        company, _, location = company_line.partition(" - ")
        signals = [l for l in rest if INDEED_SIGNAL.search(l)]
        snippet = max((l for l in rest if l not in signals), key=len, default="")
        jk = re.search(r"[?&]jk=([0-9a-f]+)", lines[url_at], re.I)
        if jk:
            job_id, link = jk.group(1).lower(), f"https://in.indeed.com/viewjob?jk={jk.group(1).lower()}"
        else:
            # Sponsored: no job ID. Never keep the personalised click link.
            job_id = "ad-" + hashlib.sha1(f"{title}|{company}|{location}".lower().encode()).hexdigest()[:12]
            link = f"https://in.indeed.com/jobs?q={quote_plus(f'{title} {company}')}&l={quote_plus(location)}"
            signals.append("Sponsored")
        if job_id in seen:
            continue
        seen.add(job_id)
        record = _record("Indeed", job_id, link, [title, company.strip(), location.strip()], received, query, snippet)
        record["signals"] = signals
        jobs.append(record)
    return jobs


def parse_alert(mail: dict) -> list[dict]:
    """mail: {from, date, body, ...} -> job records. Not a LinkedIn/Indeed alert -> []."""
    source = source_of(mail.get("from", ""))
    if source == "LinkedIn":
        return parse_linkedin(mail.get("body", ""), mail.get("date", ""))
    if source == "Indeed":
        return parse_indeed(mail.get("body", ""), mail.get("date", ""))
    return []
