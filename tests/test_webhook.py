import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from reviewpilot.api.app import app

SECRET = "test-secret"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


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


def test_valid_pr_event_is_logged(caplog):
    with caplog.at_level("INFO", logger="reviewpilot"):
        r = post(PAYLOAD, sign(PAYLOAD))
    assert r.status_code == 200
    assert "repo=me/test pr=#1 head=abc123" in caplog.text


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
    assert r.status_code == 200 and r.json()["status"] == "ignored"
