import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from reviewpilot.agents.graph import Finding, checkpointer
from reviewpilot.config import Settings
from reviewpilot.mcp_server import server
from reviewpilot.queue.jobs import job_key
from test_agents import ctx

TOOLS = {
    "get_pr_context": {"repo": "string", "number": "integer"},
    "review_file": {"repo": "string", "number": "integer", "path": "string"},
    "run_tests_sandboxed": {"repo": "string", "number": "integer"},
    "list_findings": {"repo": "string", "number": "integer"},
}


def test_tool_schemas_and_read_only():
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert set(tools) == set(TOOLS)  # no posting tool
    for name, props in TOOLS.items():
        schema = tools[name].input_schema
        assert {k: v["type"] for k, v in schema["properties"].items()} == props
        assert set(schema["required"]) == set(props)
        assert tools[name].annotations.read_only_hint is True


def test_stdout_is_only_json_rpc():
    """Logging must go to stderr: any stray stdout line would corrupt the protocol."""
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]  # fmt: skip
    p = subprocess.Popen(
        [sys.executable, "-m", "reviewpilot.mcp_server"], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=Path(__file__).parents[1],
    )  # fmt: skip
    try:
        for m in msgs:
            p.stdin.write(json.dumps(m) + "\n")
            p.stdin.flush()
        # read until the tools/list reply; closing stdin early would race the server's replies
        replies = []
        while not replies or replies[-1].get("id") != 2:
            line = p.stdout.readline()
            assert line, "server exited early"
            replies.append(json.loads(line))  # raises if any stdout line is not JSON
    finally:
        p.stdin.close()
        err = p.stderr.read()
        p.wait(timeout=30)
    assert all(r["jsonrpc"] == "2.0" for r in replies)
    assert {t["name"] for t in replies[-1]["result"]["tools"]} == set(TOOLS)
    assert "INFO" in err  # logging is on, and it went to stderr


def test_repo_guard(monkeypatch):
    monkeypatch.setattr(server, "get_settings", lambda: Settings(allowed_repos="Me/ok, me/two"))
    with pytest.raises(ValueError, match="owner/name"):
        server._client("../etc")
    with pytest.raises(ValueError, match="ALLOWED_REPOS"):
        server._client("me/other")


def test_app_not_installed_is_readable(monkeypatch):
    from github import GithubException

    def boom(owner, repo):
        raise GithubException(404, {}, {})

    monkeypatch.setattr(server, "get_settings", lambda: Settings(allowed_repos=""))
    monkeypatch.setattr("reviewpilot.github.auth.installation_client", boom)
    with pytest.raises(ValueError, match="not installed"):
        server._client("me/ok")


def test_get_pr_context_and_review_file(monkeypatch):
    c = ctx()
    monkeypatch.setattr(server, "_context", lambda repo, n: (None, ctx()))
    out = server.get_pr_context("me/r", 1)
    assert out["head_sha"] == c.head_sha and any(f["path"] == "app/calc.py" for f in out["files"])
    with pytest.raises(ValueError, match="not a reviewable"):
        server.review_file("me/r", 1, "nope.py")


def test_list_findings_reads_checkpoint(monkeypatch, tmp_path):
    sha = "abc"
    gh = SimpleNamespace(get_repo=lambda r: SimpleNamespace(
        get_pull=lambda n: SimpleNamespace(head=SimpleNamespace(sha=sha))))  # fmt: skip
    db = str(tmp_path / "cp.sqlite")
    monkeypatch.setattr(server, "_client", lambda repo: gh)
    monkeypatch.setattr(server, "get_settings", lambda: Settings(checkpoint_db=db))
    assert server.list_findings("me/r", 1)["reviewed"] is False  # no db yet

    f = Finding(file="a.py", line=3, severity="high", category="bug", message="m", confidence=0.9)
    saver = checkpointer(db)
    saver.put(
        {"configurable": {"thread_id": job_key("me/r", 1, sha), "checkpoint_ns": ""}},
        {"v": 1, "id": "1", "ts": "2026-01-01T00:00:00+00:00",
         "channel_values": {"inline": [f], "summary": [], "posted": True},
         "channel_versions": {}, "versions_seen": {}},
        {"source": "loop", "step": 0}, {},
    )  # fmt: skip
    out = server.list_findings("me/r", 1)
    assert out["reviewed"] and out["posted"] and out["inline"][0]["message"] == "m"
    assert server.list_findings("me/r", 2)["reviewed"] is False  # other PR number = other thread
