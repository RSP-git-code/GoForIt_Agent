"""Shared state passed between the agents in the LangGraph pipeline (CLAUDE.md §4.2).

Each node receives the whole state and returns only the keys it changes.
LangGraph merges those updates in. `trace` and `warnings` use an "add" reducer,
so nodes append to them instead of replacing them.
"""

import operator
from typing import Annotated, TypedDict


class FillState(TypedDict, total=False):
    fields: list[dict]                 # FieldDescriptor dicts from the extension
    job_description: str | None
    profile: dict                      # never logged
    classified: list[dict]             # Page Analyzer: {field_id, key, source, confidence}
    fill_plan: list[dict]              # Mapper: FillAction dicts
    free_text_fields: list[str]        # field ids the Drafter should answer
    fit: dict | None                   # Matcher output
    drafts: dict[str, dict]            # Drafter: field_id -> {text, ...}
    verification: dict[str, dict]      # Verifier: field_id -> {passed, reasons}
    retries: dict[str, int]            # field_id -> how many times re-drafted
    warnings: Annotated[list[str], operator.add]
    trace: Annotated[list[str], operator.add]
    actions: list[dict]                # Assemble: final plan sent to the extension
    llm: bool                          # this request may use the local LLM (POST /draft; "AI drafts" switch)
