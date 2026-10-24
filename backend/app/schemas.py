"""Request/response models for the backend API.

The extension sends DOM-free field descriptors (see extension/content/extractor.js)
and gets back one FillAction per field.
"""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["filled", "review", "missing", "skipped"]


class FieldDescriptor(BaseModel):
    id: str
    label: str = ""
    placeholder: str = ""
    name: str = ""
    element_id: str = ""
    aria_label: str = ""
    helper_text: str = ""
    kind: str = "text"  # text, email, tel, number, date, month, url, textarea, select, radio, checkbox, combobox, file
    options: list[str] = Field(default_factory=list)
    required: bool = False
    max_length: int | None = None
    readonly: bool = False  # e.g. a calendar date picker's text box
    section: str = ""       # heading of the section the field is in ("Websites", "Education")


class RunFillRequest(BaseModel):
    fields: list[FieldDescriptor]
    job_description: str | None = None
    profile: dict  # never logged (CLAUDE.md rule 4)


class FillAction(BaseModel):
    field_id: str
    key: str | None = None  # profile key the field maps to, e.g. "personal.email"
    status: Status
    # Text to type, the option text to pick, or a list of option texts to tick.
    value: str | list[str] | None = None
    reason: str = ""
    source: str = "rules"  # which agent decided: rules, classifier, draft
    # "tags": a tag box (Workday "Type to Add Skills"): add each value one at a time by picking
    # it from the suggestions that appear, instead of typing the whole list into the box.
    mode: str = ""


class RunFillResponse(BaseModel):
    actions: list[FillAction]
    warnings: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)  # agent nodes visited, in order
    fit: dict | None = None
    draftable: list[str] = Field(default_factory=list)  # field ids an AI draft could answer (POST /draft)


class DraftRequest(BaseModel):
    field: FieldDescriptor
    job_description: str | None = None
    profile: dict  # never logged (CLAUDE.md rule 4)


class DraftResponse(BaseModel):
    action: FillAction
    trace: list[str] = Field(default_factory=list)


class CoachRequest(BaseModel):
    job_text: str                      # the job description the student pasted (or a company page's text)
    job_title: str = ""
    profile: dict  # never logged (CLAUDE.md rule 4)


class JobFileRequest(BaseModel):
    name: str                          # file name, e.g. "QC Associate JD.pdf"
    data_base64: str                   # the file's bytes as base64 (JSON can't carry raw bytes)


class OctoRequest(BaseModel):
    message: str                       # what the student typed or pasted
    job_title: str = ""
    last_result: dict | None = None    # the Coach analysis of the job being discussed (from the previous reply)
    plan: dict | None = None           # the study plan so far (agents/octo_plan.py), from the previous reply
    history: list[dict] = Field(default_factory=list)  # recent turns: {role, text}
    profile: dict  # never logged (CLAUDE.md rule 4)
