"""Fair benchmark: rules alone vs rules + Form Reader on questions the rules were NOT tuned on.

    backend/.venv/Scripts/python ml/llm/unseen_bench.py qwen3:4b

Uses the Phase 5 TEST split (held-out companies + my 3 real forms) with their
checked labels. The correct answer for a field is what the made-up student's
profile gives for its checked label (or "leave it empty" for label "none").
Free-text, Yes/No, consent and upload fields are left out: other agents handle those.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml" / "classifier"))
sys.path.insert(0, str(ROOT / "ml" / "llm"))

from agents.form_reader import read_form  # noqa: E402
from agents.mapper import map_field  # noqa: E402
from build_dataset import TEST, load_descriptors  # noqa: E402
from form_reader_bench import PROFILE, rules_answers, score  # noqa: E402
from services.field_text import field_text  # noqa: E402

SKIP_LABELS = {"free_text_question", "yes_no_question", "consent", "resume_file", "file_other"}


def test_pages() -> dict[str, list[tuple[dict, list | None]]]:
    labels = {(r["source"], r["text"]): r["label"]
              for r in csv.DictReader(open(ROOT / "ml/classifier/data/labels.csv", encoding="utf-8-sig"))}
    pages, seen = defaultdict(list), set()
    for d in load_descriptors():
        label = labels.get((d["source"], field_text(d)))
        if d["source"] not in TEST or not label or label in SKIP_LABELS:
            continue
        key = (d["source"], field_text(d))
        if key in seen:
            continue
        seen.add(key)
        field = {**d, "id": f"f{len(seen)}"}
        if label == "none":
            expected = None
        else:
            value = map_field(field, label, PROFILE).get("value")
            value = ", ".join(value) if isinstance(value, list) else value
            expected = [str(value)] if value not in (None, "") else None
        pages[d["source"]].append((field, expected))
    return pages


def run(model: str | None) -> dict:
    totals = defaultdict(int)
    misses = []
    for source, page in test_pages().items():
        fields = [f for f, _ in page]
        by_rules = rules_answers(fields)
        llm = {}
        if model:
            for i in range(0, len(fields), 20):  # long forms in chunks of 20
                answers, secs = read_form(fields[i:i + 20], PROFILE, model, today=date(2026, 10, 18))
                llm.update(answers)
                totals["seconds"] += secs
                totals["calls"] += 1
        for f, expected in page:
            totals["fields"] += 1
            rule_answer, key = by_rules[f["id"]]
            ok, bad = score(rule_answer, expected)
            totals["rules_ok"] += ok
            totals["rules_invented"] += bad
            a = llm.get(f["id"], {})
            llm_answer = a.get("answer") if a.get("ok") and a.get("answer") not in ("null", "") else None
            final = rule_answer if rule_answer is not None or key == "yes_no_question" else llm_answer
            ok2, bad2 = score(final, expected)
            totals["hybrid_ok"] += ok2
            totals["hybrid_invented"] += bad2
            if ok2 and not ok:
                totals["llm_fixed"] += 1
            if model and (ok2 != ok or bad2):
                misses.append((source, f["label"][:55], expected, rule_answer, llm_answer, "fixed" if ok2 else "WRONG"))
    return {"totals": dict(totals), "changes": misses}


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else None
    r = run(model)
    t = r["totals"]
    print(f"{t['fields']} unseen fields | rules alone: {t['rules_ok']} correct, {t['rules_invented']} invented")
    if model:
        print(f"rules + {model}: {t['hybrid_ok']} correct, {t['hybrid_invented']} invented, LLM fixed {t.get('llm_fixed', 0)}, "
              f"{t['seconds'] / max(t['calls'], 1):.0f} s per page")
        for row in r["changes"]:
            print("  ", row)
