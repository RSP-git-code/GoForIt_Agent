"""Phase 6: train the field classifier.

    backend/.venv/Scripts/python ml/classifier/train.py            # TF-IDF baseline + MiniLM fine-tune
    backend/.venv/Scripts/python ml/classifier/train.py --epochs 4  # quicker run

Reads data/fields.jsonl (train/val splits only; test is never touched here).
Saves models/field-classifier/ (MiniLM, used by the backend) and
models/tfidf.joblib (baseline). Then run evaluate.py.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import accuracy_score, f1_score  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from transformers import AutoModel, AutoTokenizer, get_linear_schedule_with_warmup  # noqa: E402

from services.classifier import BASE_MODEL, MAX_TOKENS, MODEL_DIR  # noqa: E402
from services.classifier_model import FieldClassifier  # noqa: E402

DATA = HERE / "data" / "fields.jsonl"
MODELS = HERE / "models"


def load(split: str) -> list[dict]:
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf8").splitlines() if line.strip()]
    return [r for r in rows if r["split"] == split]


def scores(gold: list[str], pred: list[str]) -> dict:
    present = sorted(set(gold))  # macro F1 over the labels this split actually has
    return {"accuracy": accuracy_score(gold, pred),
            "macro_f1": f1_score(gold, pred, labels=present, average="macro", zero_division=0)}


def train_tfidf(train, val) -> None:
    # Character n-grams handle abbreviations and typos ("percenatge", "Mob No.") without a dictionary.
    model = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1),
                          LogisticRegression(C=10, max_iter=3000))
    model.fit([r["text"] for r in train], [r["label"] for r in train])
    s = scores([r["label"] for r in val], list(model.predict([r["text"] for r in val])))
    print(f"TF-IDF + logistic regression  val accuracy {s['accuracy']:.3f}  macro F1 {s['macro_f1']:.3f}")
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS / "tfidf.joblib")


def train_minilm(train, val, epochs: int, lr: float, batch_size: int, seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    labels = sorted({r["label"] for r in train})
    index = {label: i for i, label in enumerate(labels)}
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = FieldClassifier(AutoModel.from_pretrained(BASE_MODEL), len(labels))

    def batches(rows, shuffle):
        order = list(range(len(rows)))
        if shuffle:
            random.shuffle(order)
        for i in range(0, len(order), batch_size):
            chunk = [rows[j] for j in order[i:i + batch_size]]
            enc = tokenizer([r["text"] for r in chunk], padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
            yield enc, chunk

    # The new head learns faster than the pretrained encoder, so it gets a bigger step size.
    optimizer = torch.optim.AdamW([{"params": model.encoder.parameters(), "lr": lr},
                                   {"params": model.head.parameters(), "lr": lr * 20}], weight_decay=0.01)
    steps = epochs * ((len(train) + batch_size - 1) // batch_size)
    schedule = get_linear_schedule_with_warmup(optimizer, int(0.1 * steps), steps)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)

    best, best_state = -1.0, None
    for epoch in range(1, epochs + 1):
        model.train()
        start, total = time.time(), 0.0
        for enc, chunk in batches(train, shuffle=True):
            target = torch.tensor([index[r["label"]] for r in chunk])
            loss = loss_fn(model(**enc), target)
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            total += loss.item() * len(chunk)
        model.eval()
        pred = []
        with torch.no_grad():
            for enc, _ in batches(val, shuffle=False):
                pred += [labels[i] for i in model(**enc).argmax(-1).tolist()]
        s = scores([r["label"] for r in val], pred)
        print(f"MiniLM epoch {epoch}: train loss {total / len(train):.3f}  val accuracy {s['accuracy']:.3f}  "
              f"macro F1 {s['macro_f1']:.3f}  ({time.time() - start:.0f}s)")
        if s["macro_f1"] > best:
            best = s["macro_f1"]
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
            best_epoch = epoch

    model.load_state_dict(best_state)
    model.eval()
    model.save(MODEL_DIR, tokenizer, labels, {"base_model": BASE_MODEL, "best_epoch": best_epoch, "val_macro_f1": best,
                                               "train_examples": len(train), "trained": time.strftime("%Y-%m-%d"),
                                               "threshold": None})
    print(f"Saved best epoch {best_epoch} (val macro F1 {best:.3f}) to {MODEL_DIR}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Train the field classifier")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    train, val = load("train"), load("val")
    print(f"{len(train)} train / {len(val)} val examples, {len({r['label'] for r in train})} labels")
    train_tfidf(train, val)
    train_minilm(train, val, args.epochs, args.lr, args.batch_size, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
