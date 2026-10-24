"""Our fine-tuned field classifier (Phase 6), used by the Page Analyzer.

MiniLM (sentence-transformers/all-MiniLM-L6-v2) + mean pooling + one linear
layer, fine-tuned on ml/classifier/data/fields.jsonl by ml/classifier/train.py.
The network itself is in services/classifier_model.py.

meta() reads models/field-classifier/meta.json without loading torch, so when
the classifier is switched off ("strategy": "off") the backend never loads
torch and starts fast. If torch/transformers or the trained model are missing,
available() is False and the Page Analyzer uses the rules alone (CLAUDE.md §4.3).
Only field labels and attributes go into the model: never profile data.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from services.field_text import field_text

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "classifier" / "models" / "field-classifier"
MAX_TOKENS = 96


def _switched_off() -> bool:
    # GOFORIT_CLASSIFIER=off: rules only (the test suite uses this so results don't depend on the trained model).
    return os.environ.get("GOFORIT_CLASSIFIER", "").lower() == "off"


def meta() -> dict:
    """The trained model's settings (strategy, threshold, scores), or {} if there's no model."""
    path = MODEL_DIR / "meta.json"
    if _switched_off() or not (MODEL_DIR / "head.pt").exists() or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except ValueError:
        return {}


@lru_cache(maxsize=1)
def _loaded():
    if not meta():
        return None
    from services.classifier_model import FieldClassifier  # loads torch: only now
    return FieldClassifier.load(MODEL_DIR)


def available() -> bool:
    try:
        return _loaded() is not None
    except Exception:  # torch missing or a broken model file must not break filling
        return False


def predict_texts(texts: list[str]) -> list[tuple[str, float]]:
    """(label, confidence) for each input text."""
    from services.classifier_model import predict_texts as run
    model, tokenizer, labels = _loaded()
    return run(model, tokenizer, labels, texts, MAX_TOKENS)


def predict(fields: list[dict]) -> list[tuple[str, float]]:
    return predict_texts([field_text(f) for f in fields])
