import json
import logging

from fastapi import FastAPI, HTTPException, Request

from reviewpilot.config import get_settings
from reviewpilot.github.webhook import verify_signature

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("reviewpilot")

app = FastAPI(title="ReviewPilot")


@app.post("/webhook")
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
    pr = payload.get("pull_request", {})
    log.info(
        "pull_request %s repo=%s pr=#%s head=%s",
        payload.get("action"),
        payload.get("repository", {}).get("full_name"),
        pr.get("number"),
        pr.get("head", {}).get("sha"),
    )
    return {"status": "received"}
