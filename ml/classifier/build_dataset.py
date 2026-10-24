"""Phase 5: field descriptions -> labelled examples for the field classifier.

    python ml/classifier/build_dataset.py draft    # first-guess labels from the rules -> data/labels.csv
    python ml/classifier/build_dataset.py build    # labels.csv (checked) -> data/fields.jsonl + split

Step "draft" writes data/labels.csv with one row per field. Open it in Excel,
fix the "label" column where the rules guessed wrong, and put your initials in
"checked". Rows already in labels.csv keep your edits when draft runs again.

The label is the profile key the field asks for (e.g. education.class_12.percentage),
"free_text_question", "none", or one of the Mapper's special keys (consent,
yes_no_question, resume_file, skills.all...).
"""

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from services.field_text import field_text  # noqa: E402  (same text at runtime)
from services.rules import classify  # noqa: E402  (the rules baseline)

INPUTS = [DATA / "descriptors.jsonl", DATA / "greenhouse.jsonl"]
LABELS = DATA / "labels.csv"
COLUMNS = ["source", "text", "rules_label", "label", "checked", "note"]


def rules_label(d: dict) -> str:
    return classify({"id": "x", "options": [], **d}) or "none"


def load_descriptors() -> list[dict]:
    rows = []
    for path in INPUTS:
        if path.exists():
            rows += [json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    return rows


def read_labels() -> dict[tuple, dict]:
    if not LABELS.exists():
        return {}
    with LABELS.open(encoding="utf-8-sig", newline="") as fh:
        return {(r["source"], r["text"]): r for r in csv.DictReader(fh)}


def draft() -> None:
    old = read_labels()
    out, seen = [], set()
    for d in load_descriptors():
        text = field_text(d)
        key = (d["source"], text)
        if key in seen:
            continue
        seen.add(key)
        guess = rules_label(d)
        kept = old.get(key)
        out.append(kept if kept else {"source": d["source"], "text": text, "rules_label": guess,
                                      "label": guess, "checked": "", "note": ""})
    with LABELS.open("w", encoding="utf-8-sig", newline="") as fh:  # utf-8-sig: Excel shows ₹, é correctly
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(out)
    checked = sum(1 for r in out if r["checked"])
    print(f"{len(out)} fields in {LABELS} ({checked} checked, {len(out) - checked} still to check)")


# ---------- split (by source form, so no form is in two sets) ----------

# Test: my own real forms + companies never seen in training. Validation: for tuning the threshold.
TEST = {"grafyn_google_form", "confirm_application_ibm", "apply_to_a_job_amazon_jobs",
        "greenhouse_groww", "greenhouse_druva", "greenhouse_hackerrank", "greenhouse_duolingo",
        "greenhouse_okta", "greenhouse_reddit"}
VAL = {"greenhouse_rubrik", "greenhouse_coursera", "greenhouse_twilio", "greenhouse_stripe"}
FIELDS = DATA / "fields.jsonl"


def split_of(source: str) -> str:
    return "test" if source in TEST else "val" if source in VAL else "train"


def build(augment_n: int = 3, seed: int = 42) -> None:
    import random
    from collections import Counter

    from variants import augment, handwritten

    labels = read_labels()
    rng = random.Random(seed)
    examples, seen = [], set()

    def add(text, label, source, split, origin, rules=None):
        key = (text.lower(), label, split)
        if key not in seen:
            seen.add(key)
            example = {"text": text, "label": label, "source": source, "split": split, "origin": origin}
            if rules is not None:
                example["rules"] = rules  # what the rules predict: the Phase 6 baseline, same rows
            examples.append(example)

    for d in load_descriptors():
        row = labels.get((d["source"], field_text(d)))
        if not row:
            continue  # not labelled yet (run draft)
        split = split_of(d["source"])
        add(field_text(d), row["label"], d["source"], split, "real", rules_label(d))
        if split == "train":
            for v in augment(d, row["label"], rng, augment_n):
                add(field_text(v), row["label"], d["source"], split, "augmented")
    for d in handwritten():
        add(field_text(d), d["label_key"], "handwritten", "train", "handwritten")
        for v in augment(d, d["label_key"], rng, augment_n):
            add(field_text(v), d["label_key"], "handwritten", "train", "augmented")

    FIELDS.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in examples), encoding="utf8")
    by_split = Counter(e["split"] for e in examples)
    origins = Counter((e["split"], e["origin"]) for e in examples)
    train_labels = {e["label"] for e in examples if e["split"] == "train"}
    unseen = sorted({e["label"] for e in examples if e["split"] != "train"} - train_labels)
    print(f"{len(examples)} examples -> {FIELDS.name}: " + ", ".join(f"{s} {by_split[s]}" for s in ("train", "val", "test")))
    print("  train by origin: " + ", ".join(f"{o} {n}" for (s, o), n in sorted(origins.items()) if s == "train"))
    print(f"  {len(train_labels)} labels in train" + (f"; in val/test but never in train: {unseen}" if unseen else ""))
    for split in ("val", "test"):
        rows = [e for e in examples if e["split"] == split]
        hits = sum(e["rules"] == e["label"] for e in rows)
        print(f"  rules baseline on {split}: {hits}/{len(rows)} = {hits / len(rows):.1%}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "draft"
    if step == "draft":
        draft()
    elif step == "build":
        sys.path.insert(0, str(HERE))
        build()
    else:
        print(f"Unknown step {step!r}. Use: draft | build")
