"""POST /run-fill: runs the agent pipeline and returns a fill plan.

The request contains the student's profile, so nothing from it is logged
(CLAUDE.md rule 4). Only counts are logged.
"""

import logging

from fastapi import APIRouter, HTTPException

from agents.coach import coach
from agents.octo_chat import reply as octo_reply
from agents.graph import draft_one, run_fill
from services.job_file import FileError, read_job_file
from app.schemas import CoachRequest, JobFileRequest, OctoRequest, DraftRequest, DraftResponse, RunFillRequest, RunFillResponse

router = APIRouter()
log = logging.getLogger("goforit.run_fill")


@router.post("/run-fill", response_model=RunFillResponse)
def run_fill_route(req: RunFillRequest) -> RunFillResponse:
    result = run_fill([f.model_dump() for f in req.fields], req.profile, req.job_description)
    # One summary line per Fill, to see what happened on a site from this window. Only the form's
    # own labels are printed (the questions), never a value from the profile (CLAUDE.md rule 4).
    by_id = {f.id: f for f in req.fields}
    counts = {}
    for a in result["actions"]:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
    def labels(status: str) -> str:
        names = [(by_id[a["field_id"]].label or f"(no label, {by_id[a['field_id']].kind}"
                  f"{', name ' + by_id[a['field_id']].name[:30] if by_id[a['field_id']].name else ''})")[:50]
                 for a in result["actions"] if a["status"] == status and a["field_id"] in by_id]
        return "; ".join(names[:20]) + (" …" if len(names) > 20 else "")
    log.info("run-fill: %d fields -> %s", len(req.fields), ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    for status in ("missing", "skipped"):
        if counts.get(status):
            log.info("  %s: %s", status, labels(status))
    return RunFillResponse(**result)


@router.post("/draft", response_model=DraftResponse)
def draft_route(req: DraftRequest) -> DraftResponse:
    """One AI-drafted written answer (local LLM, Drafter <-> Verifier). Called after Fill, one question
    at a time, only when the "AI drafts" switch is on. The answer text is never logged."""
    result = draft_one(req.field.model_dump(), req.profile, req.job_description)
    log.info("draft: path %s, status %s", " > ".join(result["trace"]), result["action"]["status"])
    return DraftResponse(**result)


@router.post("/coach")
def coach_route(req: CoachRequest) -> dict:
    """Agent Octo: fit, missing skills (with free resources) and hard requirements for one job description.
    Deterministic, no LLM. Neither the job text nor the profile is logged."""
    result = coach(req.job_text[:20000], req.profile, req.job_title)
    log.info("coach: %d skills asked, fit %s", result["skills_asked"], result["fit_percent"])
    return result


@router.post("/octo")
def octo_route(req: OctoRequest) -> dict:
    """Agent Octo chat: one message in, Octo's replies out. Messages are never logged."""
    out = octo_reply(req.message[:20000], req.profile, req.last_result, req.history, req.job_title, req.plan)
    log.info("octo: %d replies, mood %s", len(out["messages"]), out["mood"])
    return out


@router.post("/octo/read-file")
def octo_read_file_route(req: JobFileRequest) -> dict:
    """Agent Octo: text out of an uploaded job-description PDF (or .txt). Nothing is stored or logged
    except the page count."""
    try:
        out = read_job_file(req.name, req.data_base64)
    except FileError as err:
        raise HTTPException(status_code=400, detail=str(err))
    log.info("octo read-file: %d pages, %d chars", out["pages"], len(out["text"]))
    return out
