"""Page Analyzer with the classifier: strategies, threshold, safety guards (fake model, no torch needed)."""

import pytest

from agents import page_analyzer as pa
from services.field_text import field_text


def f(i, label, kind="text", options=()):
    return {"id": f"f{i}", "label": label, "kind": kind, "options": list(options), "placeholder": "", "helper_text": ""}


FIELDS = [f(0, "Secondary school leaving exam result"),                                   # rules: no key; model knows it
          f(1, "Email"),                                             # rules and model agree
          f(2, "Are you authorized to work in the United States?", "select", ["Yes", "No"]),
          f(3, "Upload transcript", "file")]
MODEL = {0: ("education.class_10.percentage", 0.95), 1: ("personal.email", 0.99),
         2: ("preferences.work_authorization_india", 0.97), 3: ("resume_file", 0.6)}


@pytest.fixture
def fake_model(monkeypatch):
    def use(strategy, threshold=0.7):
        monkeypatch.setattr(pa.classifier, "available", lambda: True)
        monkeypatch.setattr(pa.classifier, "meta", lambda: {"strategy": strategy, "threshold": threshold})
        monkeypatch.setattr(pa.classifier, "predict", lambda fields: [MODEL[int(x["id"][1:])] for x in fields])
    return use


def keys(state):
    return {c["field_id"]: (c["key"], c["source"]) for c in pa.page_analyzer(state)["classified"]}


def test_off_means_rules_only(fake_model):
    fake_model("off")
    assert all(src == "rules" for _, src in keys({"fields": FIELDS}).values())


def test_model_first_uses_confident_predictions(fake_model):
    fake_model("model_first", threshold=0.9)
    k = keys({"fields": FIELDS})
    assert k["f0"] == ("education.class_10.percentage", "classifier")
    assert k["f3"][1] == "rules"  # 0.6 < 0.9: rules kept


def test_guards_apply_to_the_model(fake_model):
    fake_model("model_first", threshold=0.5)
    k = keys({"fields": FIELDS})
    assert k["f2"][0] == "yes_no_question"  # never the India answer for a US question
    assert k["f3"][0] == "file_other"       # a transcript upload is not the resume


def test_rules_first_only_fills_gaps(fake_model):
    fake_model("rules_first", threshold=0.5)
    k = keys({"fields": FIELDS})
    assert k["f1"] == ("personal.email", "rules")
    assert k["f0"][1] == "classifier"


def test_field_text_format():
    assert field_text({"label": "10th Board", "kind": "select", "options": ["CBSE", "ICSE"], "section": "Education"}) == \
        "10th Board | section: Education | type: select | options: CBSE, ICSE"
