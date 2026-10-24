"""GoForIt backend entry point.

Run from the backend/ folder:
    python -m app.main
"""

import logging
import os

import uvicorn
from fastapi import FastAPI

from app import config

# Show GoForIt's own one-line summaries (e.g. "run-fill: 23 fields -> filled 6, skipped 15")
# in the backend window, next to uvicorn's request lines.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
logging.getLogger("goforit").setLevel(logging.INFO)
from app.routes.inbox_actions import router as inbox_actions_router
from app.routes.run_fill import router as run_fill_router

app = FastAPI(title="GoForIt Backend", version=config.VERSION)
app.include_router(run_fill_router)
app.include_router(inbox_actions_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": config.VERSION}


if __name__ == "__main__":
    # Bind to localhost only (rule 4 in CLAUDE.md).
    # No auto-reload by default: it restarts the backend whenever a code file is saved, which
    # cuts off a Fill in progress. Developers can turn it on with GOFORIT_DEV=1.
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=os.environ.get("GOFORIT_DEV") == "1")
