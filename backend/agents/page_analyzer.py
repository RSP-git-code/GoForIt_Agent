"""Page Analyzer agent: decides what each form field is asking for.

Rules and our fine-tuned classifier (Phase 6) both look at every field. Which
one wins is decided by meta.json, tuned on the validation set by
ml/classifier/evaluate.py:
  - model_first: the classifier's answer when it's confident enough, else the rules'.
  - rules_first: the rules' answer when they found one, else the confident classifier.
  - off: rules only (the classifier hasn't beaten them on the test set yet).
The classifier's answer still goes through the rules' safety guards. Without
torch or a trained model, rules alone (CLAUDE.md §4.3).
"""

from services import classifier
from services.rules import FREE_TEXT, classify, guard


def _choose(field: dict, rule_key, model_label: str, conf: float, strategy: str, threshold: float):
    model_key = guard(field, model_label)
    if strategy == "model_first":
        use_model = conf >= threshold
    else:  # rules_first
        use_model = rule_key is None and conf >= threshold
    if use_model:
        return model_key, "classifier", round(conf, 3)
    return rule_key, "rules", 1.0


def page_analyzer(state: dict) -> dict:
    fields = state["fields"]
    rule_keys = [classify(f) for f in fields]
    warnings = []
    # meta() is a small JSON read; the model (and torch) load only if it's switched on.
    meta = classifier.meta() if fields else {}
    if meta and meta.get("strategy") != "off" and classifier.available():  # "off": hasn't beaten the rules yet
        strategy, threshold = meta.get("strategy") or "rules_first", meta.get("threshold") or 0.7
        picks = [_choose(f, r, label, conf, strategy, threshold)
                 for f, r, (label, conf) in zip(fields, rule_keys, classifier.predict(fields))]
    else:
        picks = [(r, "rules", 1.0) for r in rule_keys]
        if fields and not meta:
            warnings.append("Field classifier not loaded: using rules only")
    classified = [{"field_id": f["id"], "key": key, "source": source, "confidence": conf}
                  for f, (key, source, conf) in zip(fields, picks)]
    free_text = [c["field_id"] for c in classified if c["key"] == FREE_TEXT]
    out = {"classified": classified, "free_text_fields": free_text, "trace": ["page_analyzer"]}
    if warnings:
        out["warnings"] = warnings
    return out
