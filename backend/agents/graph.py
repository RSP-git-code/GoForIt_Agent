r"""The LangGraph pipeline behind POST /run-fill (diagram in docs/AGENTS.md).

    page_analyzer -> mapper --(no free-text fields)---------------------> assemble
                           \--(free text, LLM offline)--> llm_offline --> assemble
                           \--(free text)--> matcher -> drafter -> verifier
                                                           ^          |
                                                           +-- retry -+ (max 2 per field)
                                                                      +--> assemble
"""

from langgraph.graph import END, START, StateGraph

from agents.drafter import drafter
from agents.mapper import mapper
from agents.matcher import matcher
from agents.page_analyzer import page_analyzer
from agents.state import FillState
from agents.verifier import verifier
from app import config
from services import ollama_client


def llm_offline(state: dict) -> dict:
    return {"warnings": ["Local LLM (Ollama) is offline: free-text answers were not drafted."], "trace": ["llm_offline"]}


def assemble(state: dict) -> dict:
    """Final plan: the Mapper's actions, with free-text fields replaced by verified drafts."""
    drafts = state.get("drafts") or {}
    verification = state.get("verification") or {}
    drafting_ran = "drafter" in (state.get("trace") or [])

    actions = []
    for action in state["fill_plan"]:
        fid = action["field_id"]
        if fid not in state["free_text_fields"]:
            actions.append(action)
            continue
        draft = drafts.get(fid) or {}
        check = verification.get(fid) or {}
        if draft.get("text") and check.get("passed"):
            actions.append({**action, "status": "review", "value": draft["text"], "source": "draft",
                            "reason": "Draft written from your profile: read and edit it before submitting"})
        elif draft.get("text"):
            reasons = "; ".join(check.get("reasons") or []) or "failed verification"
            actions.append({**action, "status": "missing", "value": None, "source": "draft",
                            "reason": f"AI draft rejected after {config.MAX_DRAFT_RETRIES} retries ({reasons}). Write this one yourself."})
        else:
            why = "no draft for this kind of question yet" if drafting_ran else "drafting is offline"
            actions.append({**action, "reason": f"Open question: write your answer ({why})"})
    return {"actions": actions, "trace": ["assemble"]}


def route_after_mapper(state: dict) -> str:
    if not state["free_text_fields"]:
        return "assemble"
    return "matcher" if ollama_client.is_available() else "llm_offline"


def route_after_verifier(state: dict) -> str:
    verification = state.get("verification") or {}
    retries = state.get("retries") or {}
    needs_retry = [
        fid for fid in state["free_text_fields"]
        if not verification.get(fid, {}).get("passed", True)
        and retries.get(fid, 0) < config.MAX_DRAFT_RETRIES
    ]
    return "drafter" if needs_retry else "assemble"


def build_graph():
    g = StateGraph(FillState)
    g.add_node("page_analyzer", page_analyzer)
    g.add_node("mapper", mapper)
    g.add_node("matcher", matcher)
    g.add_node("drafter", drafter)
    g.add_node("verifier", verifier)
    g.add_node("llm_offline", llm_offline)
    g.add_node("assemble", assemble)

    g.add_edge(START, "page_analyzer")
    g.add_edge("page_analyzer", "mapper")
    g.add_conditional_edges("mapper", route_after_mapper, ["assemble", "matcher", "llm_offline"])
    g.add_edge("llm_offline", "assemble")
    g.add_edge("matcher", "drafter")
    g.add_edge("drafter", "verifier")
    g.add_conditional_edges("verifier", route_after_verifier, ["drafter", "assemble"])
    g.add_edge("assemble", END)
    return g.compile()


GRAPH = build_graph()


def build_draft_graph():
    """One written answer with the local LLM (POST /draft), after Fill has filled the rest:

        matcher -> drafter -> verifier --(rejected, retries left)--> drafter
                                       \\--> assemble
    """
    g = StateGraph(FillState)
    g.add_node("matcher", matcher)
    g.add_node("drafter", drafter)
    g.add_node("verifier", verifier)
    g.add_node("assemble", assemble)
    g.add_edge(START, "matcher")
    g.add_edge("matcher", "drafter")
    g.add_edge("drafter", "verifier")
    g.add_conditional_edges("verifier", route_after_verifier, ["drafter", "assemble"])
    g.add_edge("assemble", END)
    return g.compile()


DRAFT_GRAPH = build_draft_graph()


def draftable(fields: list[dict], actions: list[dict]) -> list[str]:
    """Field ids that could get an AI draft: open questions, and an empty "strengths"/"about me"."""
    from agents.drafter import is_vague_question
    kinds = {f["id"]: f.get("kind") for f in fields}
    labels = {f["id"]: f.get("label") or "" for f in fields}
    return [a["field_id"] for a in actions
            if kinds.get(a["field_id"]) in ("text", "textarea") and not is_vague_question(labels[a["field_id"]])
            and (a.get("key") == "free_text_question"
                 or ((a.get("key") or "").startswith("standard_answers") and not a.get("value")))]


def draft_one(field: dict, profile: dict, job_description: str | None = None) -> dict:
    """Matcher -> Drafter <-> Verifier for ONE question with the local LLM. Returns {action, trace}."""
    if not ollama_client.ollama_running():
        return {"action": {"field_id": field["id"], "key": "free_text_question", "status": "review", "value": None,
                           "source": "draft", "reason": "Local AI (Ollama) isn't running: write this one yourself"},
                "trace": []}
    final = DRAFT_GRAPH.invoke({
        "fields": [field], "profile": profile, "job_description": job_description, "llm": True,
        "free_text_fields": [field["id"]],
        "fill_plan": [{"field_id": field["id"], "key": "free_text_question", "status": "review", "value": None,
                       "reason": "Open question: write your answer", "source": "rules"}],
        "drafts": {}, "verification": {}, "retries": {}, "warnings": [], "trace": [],
    })
    action = final["actions"][0]
    if action.get("value"):
        action = {**action, "reason": "AI draft from your profile: check every sentence before submitting"}
    return {"action": action, "trace": final.get("trace", [])}


def run_fill(fields: list[dict], profile: dict, job_description: str | None = None) -> dict:
    """Runs the pipeline and returns {actions, warnings, trace, fit}."""
    final = GRAPH.invoke({
        "fields": fields,
        "profile": profile,
        "job_description": job_description,
        "drafts": {},
        "verification": {},
        "retries": {},
        "warnings": [],
        "trace": [],
    })
    return {
        "actions": final["actions"],
        "warnings": final.get("warnings", []),
        "trace": final.get("trace", []),
        "fit": final.get("fit"),
        "draftable": draftable(fields, final["actions"]),
    }
