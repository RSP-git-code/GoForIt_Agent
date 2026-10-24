"""Collects real application-form questions from Greenhouse's public job-board API.

    python ml/classifier/collect_greenhouse.py            # all boards, 8 jobs each
    python ml/classifier/collect_greenhouse.py --jobs 4   # fewer requests

Greenhouse publishes every job's application questions as JSON for companies'
own career pages (https://developers.greenhouse.io/job-board.html). No login,
no scraping of HTML, nothing personal is sent. Requests are spaced out.

Each question becomes one field description in the same shape the extension's
extractor produces, so the classifier trains on what it will see at runtime.
Output: ml/classifier/data/greenhouse.jsonl (source = "greenhouse_<company>").
"""

import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
OUT = Path(__file__).parent / "data" / "greenhouse.jsonl"
HEADERS = {"User-Agent": "GoForIt-dataset (student portfolio project)"}

# Boards checked to exist on 2026-10-11. Mix of US tech and India-based hiring.
BOARDS = ["airbnb", "stripe", "figma", "discord", "databricks", "cloudflare", "gitlab", "mongodb",
          "twilio", "pinterest", "reddit", "gusto", "asana", "robinhood", "instacart", "lyft",
          "druva", "rubrik", "groww", "okta", "datadog", "elastic", "hackerrank", "samsara",
          "coursera", "duolingo", "waymo"]

# Greenhouse field type -> the extractor's "kind".
KINDS = {"input_text": "text", "textarea": "textarea", "input_file": "file",
         "multi_value_single_select": "select", "multi_value_multi_select": "checkbox"}

# Titles a student would apply to come first, so their questions are well covered.
STUDENT_TITLES = re.compile(r"intern|graduate|new grad|university|campus|early career|associate|junior|engineer|analyst", re.I)


def get(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def plain(text: str | None) -> str:
    """Question descriptions are HTML: keep the words only."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def descriptors(job: dict, board: str):
    groups = [("", job.get("questions") or []), ("Demographic", (job.get("demographic_questions") or {}).get("questions") or [])]
    for section, questions in groups:
        for q in questions:
            fields = [f for f in q.get("fields") or [] if f.get("type") in KINDS]
            if not fields:
                continue  # hidden fields (latitude/longitude)
            f = fields[0]  # "Resume/CV" has a file box plus a paste box: the file box is the question
            yield {
                "source": f"greenhouse_{board}",
                "form": f"greenhouse:{board}",
                "label": plain(q.get("label")),
                "section": section,
                "placeholder": "",
                "name": f.get("name") or "",
                "element_id": "",
                "aria_label": "",
                "helper_text": plain(q.get("description"))[:300],
                "kind": KINDS[f["type"]],
                "options": [plain(v.get("label")) for v in f.get("values") or []][:30],
                "required": bool(q.get("required")),
            }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=8, help="jobs per company")
    parser.add_argument("--pause", type=float, default=0.5, help="seconds between requests")
    args = parser.parse_args(argv)

    rows, seen = [], set()
    for board in BOARDS:
        try:
            jobs = get(API.format(board=board))["jobs"]
        except Exception as err:
            print(f"{board}: skipped ({type(err).__name__})")
            continue
        jobs.sort(key=lambda j: not STUDENT_TITLES.search(j.get("title", "")))
        added = 0
        for job in jobs[: args.jobs]:
            time.sleep(args.pause)
            try:
                detail = get(f"{API.format(board=board)}/{job['id']}?questions=true")
            except Exception:
                continue
            for d in descriptors(detail, board):
                # The same company asks the same questions on every job: keep one copy.
                key = (board, d["label"].lower(), d["kind"])
                if d["label"] and key not in seen:
                    seen.add(key)
                    rows.append(d)
                    added += 1
        print(f"{board}: {added} questions")
        time.sleep(args.pause)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf8")
    print(f"Wrote {len(rows)} questions from {len({r['source'] for r in rows})} companies to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
