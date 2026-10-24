"""Tests run on the rules alone unless a test turns the classifier on (tests/test_classifier.py),
and with template drafts (no local LLM) unless a test mocks the model (tests/test_llm_drafting.py)."""

import os

os.environ.setdefault("GOFORIT_CLASSIFIER", "off")
os.environ.setdefault("GOFORIT_LLM", "stub")
