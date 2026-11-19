import hashlib
import hmac
import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from reviewpilot.api.app import app
from reviewpilot.queue import jobs

SECRET = "test-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


@pytest.fixture(autouse=True)
def r(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(jobs, "connect", lambda: fake)
    return fake


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(body: bytes, signature: str | None, event: str = "pull_request"):
    headers = {"X-GitHub-Event": event}
    if signature:
        headers["X-Hub-Signature-256"] = signature
    return TestClient(app).post("/webhook", content=body, headers=headers)


PAYLOAD = json.dumps(
    {
        "action": "opened",
        "repository": {"full_name": "me/test"},
        "pull_request": {"number": 1, "head": {"sha": "abc123"}},
    }
).encode()


def test_valid_pr_event_is_logged_and_queued_once(caplog, r):
    with caplog.at_level("INFO", logger="reviewpilot"):
        res = post(PAYLOAD, sign(PAYLOAD))
    assert res.status_code == 202 and res.json()["status"] == "queued"
    assert "repo=me/test pr=#1 head=abc123" in caplog.text
    assert post(PAYLOAD, sign(PAYLOAD)).json()["status"] == "duplicate"  # GitHub redelivery
    assert r.llen(jobs.QUEUE) == 1


def test_non_review_action_not_queued(r):
    body = PAYLOAD.replace(b'"opened"', b'"closed"')
    assert post(body, sign(body)).json()["status"] == "ignored" and r.llen(jobs.QUEUE) == 0


def test_wrong_signature_rejected():
    assert post(PAYLOAD, sign(PAYLOAD, "other")).status_code == 401


def test_missing_signature_rejected():
    assert post(PAYLOAD, None).status_code == 401


def test_empty_secret_rejects_everything(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "")
    assert post(PAYLOAD, sign(PAYLOAD, "")).status_code == 401


def test_other_event_ignored():
    body = b"{}"
    r = post(body, sign(body), event="ping")
    assert r.status_code == 202 and r.json()["status"] == "ignored"
