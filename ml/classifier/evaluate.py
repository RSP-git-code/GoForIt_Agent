"""Phase 6: compare rules, TF-IDF and MiniLM on the held-out sets, and pick the threshold.

    backend/.venv/Scripts/python ml/classifier/evaluate.py

1. Tunes on VAL only: the confidence threshold below which the rules' answer is
   kept, and whether the classifier or the rules go first. Saves it to the
   model's meta.json (the backend reads it).
2. Reports once on TEST: accuracy, macro F1, the unseen-wording subset, per-class
   F1 and the top confusions. Writes outputs/report.json and outputs/confusion.csv.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

import joblib  # noqa: E402
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402

from services import classifier  # noqa: E402

DATA = HERE / "data" / "fields.jsonl"
OUT = HERE / "outputs"
THRESHOLDS = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]


def scores(gold, pred) -> dict:
    present = sorted(set(gold))
    return {"n": len(gold), "accuracy": round(accuracy_score(gold, pred), 4),
            "macro_f1": round(f1_score(gold, pred, labels=present, average="macro", zero_division=0), 4)}


def combine(strategy: str, threshold: float, model: list[tuple[str, float]], rules: list[str]) -> list[str]:
    """model_first: trust the classifier when confident, else the rules.
    rules_first: trust the rules when they found a key, else the confident classifier."""
    out = []
    for (label, conf), rule in zip(model, rules):
        if strategy == "model_first":
            out.append(label if conf >= threshold else rule)
        else:
            out.append(rule if rule != "none" else (label if conf >= threshold else rule))
    return out


def main() -> int:
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf8").splitlines() if line.strip()]
    train_texts = {r["text"].lower() for r in rows if r["split"] == "train"}
    tfidf = joblib.load(HERE / "models" / "tfidf.joblib")
    if not classifier.available():
        print("No trained MiniLM model: run train.py first.")
        return 1

    data = {}
    for split in ("val", "test"):
        xs = [r for r in rows if r["split"] == split]
        data[split] = {"rows": xs, "gold": [r["label"] for r in xs], "rules": [r["rules"] for r in xs],
                       "tfidf": list(tfidf.predict([r["text"] for r in xs])),
                       "model": classifier.predict_texts([r["text"] for r in xs])}

    # 1. Tune on validation.
    val = data["val"]
    best = max(((scores(val["gold"], combine(s, t, val["model"], val["rules"]))["accuracy"], s, t)
                for s in ("model_first", "rules_first") for t in THRESHOLDS), key=lambda x: (x[0], -x[2]))
    _, strategy, threshold = best
    print(f"Chosen on val: {strategy}, threshold {threshold}")
    meta_path = classifier.MODEL_DIR / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf8"))
    meta.update({"threshold": threshold, "strategy": strategy})
    meta_path.write_text(json.dumps(meta, indent=1), encoding="utf8")

    # 2. Report on validation and test.
    report = {"strategy": strategy, "threshold": threshold}
    for split, d in data.items():
        systems = {"rules": d["rules"], "tfidf": d["tfidf"], "minilm": [label for label, _ in d["model"]],
                   "minilm+rules": combine(strategy, threshold, d["model"], d["rules"])}
        unseen = [i for i, r in enumerate(d["rows"]) if r["text"].lower() not in train_texts]
        report[split] = {}
        print(f"\n{split.upper()} ({len(d['gold'])} fields, {len(unseen)} with wording unseen in training)")
        print(f"  {'system':14} {'accuracy':>9} {'macro F1':>9} {'unseen acc':>11}")
        for name, pred in systems.items():
            s = scores(d["gold"], pred)
            s["unseen_accuracy"] = round(sum(pred[i] == d["gold"][i] for i in unseen) / len(unseen), 4)
            report[split][name] = s
            print(f"  {name:14} {s['accuracy']:9.3f} {s['macro_f1']:9.3f} {s['unseen_accuracy']:11.3f}")

    # Details for the deployed system on test.
    test = data["test"]
    final = combine(strategy, threshold, test["model"], test["rules"])
    labels = sorted(set(test["gold"]))
    per_class = f1_score(test["gold"], final, labels=labels, average=None, zero_division=0)
    support = Counter(test["gold"])
    report["test_per_class_f1"] = {label: {"f1": round(float(f), 3), "n": support[label]} for label, f in zip(labels, per_class)}
    confusions = Counter((g, p) for g, p in zip(test["gold"], final) if g != p)
    report["test_top_confusions"] = [{"gold": g, "predicted": p, "count": n} for (g, p), n in confusions.most_common(15)]
    report["test_fixed_vs_rules"] = sum(f == g != r for f, g, r in zip(final, test["gold"], test["rules"]))
    report["test_broken_vs_rules"] = sum(r == g != f for f, g, r in zip(final, test["gold"], test["rules"]))
    print(f"\nTest, minilm+rules vs rules alone: fixed {report['test_fixed_vs_rules']}, broke {report['test_broken_vs_rules']}")
    print("Top confusions (gold -> predicted):")
    for c in report["test_top_confusions"][:8]:
        print(f"  {c['count']}x {c['gold']} -> {c['predicted']}")

    OUT.mkdir(exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf8")
    all_labels = sorted(set(test["gold"]) | set(final))
    with (OUT / "confusion.csv").open("w", encoding="utf8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["gold \\ predicted"] + all_labels)
        pairs = Counter(zip(test["gold"], final))
        for g in all_labels:
            w.writerow([g] + [pairs.get((g, p), 0) for p in all_labels])
    print(f"\nWrote {OUT / 'report.json'} and {OUT / 'confusion.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
