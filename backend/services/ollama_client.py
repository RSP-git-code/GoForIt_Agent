"""Talks to the local Ollama server (127.0.0.1:11434). Only localhost, ever.

config.LLM_BACKEND: "ollama" (Drafter/Verifier use the local model) or "stub"
(template drafts, rule checks only; the test suite uses this). Set it with the
GOFORIT_LLM environment variable.
"""

import json
import time
import urllib.request

from app import config


def ollama_running(timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(f"{config.OLLAMA_URL}/api/tags", timeout=timeout) as resp:
            return resp.status == 200
    except OSError:
        return False


def is_available() -> bool:
    if config.LLM_BACKEND == "stub":
        return True
    return ollama_running()


def use_llm(state: dict | None = None) -> bool:
    """True when drafts should come from the local model (not templates): the request asked for it
    (state["llm"], set by POST /draft) or GOFORIT_LLM=ollama, and Ollama is running."""
    wanted = (state or {}).get("llm")
    if wanted is None:
        wanted = config.LLM_BACKEND == "ollama"
    return bool(wanted) and ollama_running()


def chat(system: str, user: str, model: str | None = None, schema: dict | None = None,
         temperature: float = 0.2, timeout: float | None = None) -> tuple[str, float]:
    """One chat request to the local model. Returns (reply text, seconds). Raises OSError if Ollama fails."""
    model = model or config.DRAFT_MODEL
    body = {"model": model, "stream": False, "keep_alive": "30m",
            "options": {"temperature": temperature, "num_ctx": 6144},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if schema:
        body["format"] = schema
    if model.startswith("qwen3"):
        body["think"] = False  # Qwen3 "thinks" out loud by default: slow, and not needed here
    req = urllib.request.Request(f"{config.OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout or config.LLM_TIMEOUT) as resp:
        reply = json.load(resp)
    return reply["message"]["content"], time.time() - start
