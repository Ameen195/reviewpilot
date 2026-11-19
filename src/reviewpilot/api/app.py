"""Run: python -m reviewpilot.api.app  (binds to 127.0.0.1 only)"""

import json
import logging
from html import escape
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from reviewpilot.config import get_settings
from reviewpilot.github.webhook import verify_signature
from reviewpilot.queue import jobs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reviewpilot")

app = FastAPI(title="ReviewPilot")
REVIEW_ACTIONS = {"opened", "synchronize", "reopened"}


@app.post("/webhook", status_code=202)
async def webhook(request: Request):
    body = await request.body()
    secret = get_settings().github_webhook_secret
    if not verify_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="invalid signature")

    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="invalid json")
    action = payload.get("action")
    repo = payload.get("repository", {}).get("full_name")
    pr = payload.get("pull_request", {})
    number, sha = pr.get("number"), pr.get("head", {}).get("sha")
    log.info("pull_request %s repo=%s pr=#%s head=%s", action, repo, number, sha)
    if action not in REVIEW_ACTIONS:
        return {"status": "ignored", "action": action}
    if not (isinstance(repo, str) and isinstance(number, int) and isinstance(sha, str)):
        raise HTTPException(status_code=400, detail="missing repo, number or head sha")
    queued = jobs.enqueue(jobs.connect(), repo, number, sha)
    return {"status": "queued" if queued else "duplicate"}


@app.get("/approvals", response_class=HTMLResponse)
def approvals():
    rows = []
    for key, item in jobs.list_pending(jobs.connect()).items():
        findings = "".join(
            f"<li><code>{escape(f['file'])}:{f['line'] or ''}</code> {escape(f['message'])}</li>"
            for f in item["critical"]
        )
        buttons = "".join(
            f'<form method="post" action="/approvals?key={quote(key, safe="")}&amp;decision={d}" '
            f'style="display:inline"><button>{d.title()}</button></form> '
            for d in ("approve", "reject")
        )
        rows.append(f"<section><h2>{escape(key)}</h2><ul>{findings}</ul>{buttons}</section>")
    body = "".join(rows) or "<p>Nothing waiting for approval.</p>"
    return (
        "<!doctype html><meta charset=utf-8><title>ReviewPilot approvals</title>"
        "<h1>Critical findings waiting for approval</h1>"
        "<p>Approve: post them. Reject: post the review without them.</p>" + body
    )


@app.post("/approvals")
def decide(request: Request, key: str = Query(), decision: str = Query()):
    origin = request.headers.get("origin")
    if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
        raise HTTPException(status_code=403, detail="cross-site request")  # other sites can't click
    if decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")
    if not jobs.decide(jobs.connect(), key, decision):
        raise HTTPException(status_code=404, detail="not waiting for approval")
    log.info("approval %s: %s", key, decision)
    return RedirectResponse("/approvals", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
