"""Queue, worker durability, approval and posting. Offline: fakeredis, temp SQLite, fake GitHub."""

import json
from types import SimpleNamespace

import fakeredis
import pytest
import redis
from fastapi.testclient import TestClient

from reviewpilot.agents.graph import Finding, checkpointer
from reviewpilot.api import app as api
from reviewpilot.github.post import MARKER, post_review
from reviewpilot.queue import jobs
from reviewpilot.queue.worker import process
from test_agents import ctx


@pytest.fixture
def r(monkeypatch):
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(jobs, "connect", lambda: fake)
    return fake


# ---------- queue ----------


def test_same_head_commit_is_queued_once(r):
    assert jobs.enqueue(r, "me/t", 1, "abc")
    assert not jobs.enqueue(r, "me/t", 1, "abc")  # redelivery / reopen
    assert jobs.enqueue(r, "me/t", 1, "def")  # new push
    assert r.llen(jobs.QUEUE) == 2


def test_job_stays_in_processing_until_done_and_recovers_after_restart(r):
    jobs.enqueue(r, "me/t", 1, "a")
    jobs.enqueue(r, "me/t", 2, "b")
    raw = jobs.next_job(r, timeout=1)
    assert json.loads(raw)["number"] == 1 and r.lrange(jobs.PROCESSING, 0, -1) == [raw]
    # worker killed here; a new worker starts
    assert jobs.recover(r) == 1 and r.llen(jobs.PROCESSING) == 0
    assert jobs.next_job(r, timeout=1) == raw  # the killed job runs first again
    jobs.done(r, raw)
    assert r.llen(jobs.PROCESSING) == 0


def test_socket_timeout_while_idle_means_no_job_and_loses_nothing(r, monkeypatch):
    jobs.enqueue(r, "me/t", 1, "a")

    def blmove_then_timeout(src, dst, timeout, a, b):
        r.lmove(src, dst, a, b)  # server moved the job, but the reply never arrived
        raise redis.TimeoutError("Timeout reading from socket")

    monkeypatch.setattr(r, "blmove", blmove_then_timeout)
    assert jobs.next_job(r, timeout=1) is None
    assert r.llen(jobs.PROCESSING) == 0 and r.llen(jobs.QUEUE) == 1  # job put back


def test_socket_timeout_is_longer_than_block_timeout(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    kw = jobs.connect().connection_pool.connection_kwargs
    assert kw["socket_timeout"] > jobs.BLOCK_TIMEOUT


def test_failed_job_can_be_queued_again(r):
    jobs.enqueue(r, "me/t", 1, "a")
    jobs.forget(r, jobs.job_key("me/t", 1, "a"))
    assert jobs.enqueue(r, "me/t", 1, "a")


def test_decision_resumes_once(r):
    job = {"key": "k", "repo": "me/t", "number": 1, "sha": "a"}
    jobs.add_pending(r, job, [{"file": "a.py", "line": 1, "message": "m"}])
    assert jobs.decide(r, "k", "approve")
    assert not jobs.decide(r, "k", "approve")  # double click
    assert json.loads(r.lpop(jobs.QUEUE)) == {**job, "resume": "approve"}


# ---------- worker: pause, resume, crash ----------


def llm_with(severity, calls):
    def llm(model, system, user):
        calls.append(model)
        if "File: app/calc.py" in user and "logic" in system:
            msg = {"line": 6, "severity": severity, "message": "bad", "confidence": 0.9}
            return {"findings": [msg]}, 5
        return {"findings": []}, 5

    return llm


def setup_with(posts, crash_first=False):
    c = ctx()

    def post(state):
        if crash_first and not posts:
            posts.append("crash")
            raise KeyboardInterrupt  # simulated kill mid-run (not caught as Exception)
        posts.append(state)
        return True

    return lambda job: (c, None, post), c


def job_for(c, r):
    jobs.enqueue(r, "me/t", c.number, c.head_sha)
    return jobs.next_job(r, timeout=1)


def test_critical_finding_waits_for_approval_then_posts_once(r, tmp_path):
    saver, calls, posts = checkpointer(str(tmp_path / "cp.sqlite")), [], []
    setup, c = setup_with(posts)
    raw = job_for(c, r)
    assert process(r, raw, saver, setup, llm_with("critical", calls)) == "paused"
    (pending,) = jobs.list_pending(r).values()
    assert posts == [] and pending["critical"][0]["message"] == "bad"

    key = json.loads(raw)["key"]
    assert jobs.decide(r, key, "reject")
    resume = r.lpop(jobs.QUEUE)
    n = len(calls)
    assert process(r, resume, saver, setup, llm_with("critical", calls)) == "posted"
    assert len(calls) == n  # resumed from checkpoint: reviewers not called again
    assert posts[0]["inline"] == [] and posts[0]["rejected"] == 1
    assert process(r, resume, saver, setup, llm_with("critical", calls)) == "not-waiting"
    assert process(r, raw, saver, setup, llm_with("critical", calls)) == "already-done"
    assert len(posts) == 1


def test_killed_worker_resumes_from_checkpoint_without_redoing_work(r, tmp_path):
    db, calls, posts = str(tmp_path / "cp.sqlite"), [], []
    setup, c = setup_with(posts, crash_first=True)
    raw = job_for(c, r)
    with pytest.raises(KeyboardInterrupt):
        process(r, raw, checkpointer(db), setup, llm_with("high", calls))
    n = len(calls)
    assert n > 0

    jobs.recover(r)  # restart: new worker, new SQLite connection
    raw2 = jobs.next_job(r, timeout=1)
    assert process(r, raw2, checkpointer(db), setup, llm_with("high", calls)) == "posted"
    assert len(calls) == n  # no LLM call repeated
    assert posts[0] == "crash" and len(posts) == 2
    assert [f.message for f in posts[1]["inline"]] == ["bad"]


def test_stale_job_is_skipped(r, tmp_path):
    setup, c = setup_with([])
    jobs.enqueue(r, "me/t", c.number, "old-sha")
    raw = jobs.next_job(r, timeout=1)
    assert process(r, raw, checkpointer(str(tmp_path / "cp.sqlite")), setup) == "stale"


# ---------- posting ----------


class FakePR:
    def __init__(self, bodies=()):
        self.reviews = [SimpleNamespace(body=b) for b in bodies]
        self.created = []

    def get_reviews(self):
        return self.reviews

    def create_review(self, **kw):
        self.created.append(kw)


def fake_gh(pr):
    repo = SimpleNamespace(get_pull=lambda n: pr, get_commit=lambda sha: sha)
    return SimpleNamespace(get_repo=lambda name: repo)


def F(**kw):
    base = {"file": "app/calc.py", "line": 6, "severity": "high", "category": "bug",
            "message": "m", "confidence": 0.9}  # fmt: skip
    return Finding(**{**base, **kw})


def test_post_is_comment_only_with_marker_and_bump_note():
    pr, c = FakePR(), ctx()
    state = {"inline": [F(bumped_by_tests=True)], "summary": [F(line=None, message="pr-level")]}
    assert post_review(fake_gh(pr), "me/t", c, state)
    (kw,) = pr.created
    assert kw["event"] == "COMMENT"
    assert kw["comments"] == [{"path": "app/calc.py", "line": 6, "side": "RIGHT",
                               "body": kw["comments"][0]["body"]}]  # fmt: skip
    assert "severity raised: failing test" in kw["comments"][0]["body"]
    assert MARKER.format(sha=c.head_sha) in kw["body"] and "pr-level" in kw["body"]


def test_post_skipped_when_marker_already_present():
    c = ctx()
    pr = FakePR([None, "old review " + MARKER.format(sha=c.head_sha)])
    assert not post_review(fake_gh(pr), "me/t", c, {"inline": [F()]})
    assert pr.created == []


# ---------- approval API ----------


def test_approval_page_and_decision(r):
    jobs.add_pending(r, {"key": "me/t#1@a"}, [{"file": "a.py", "line": 3, "message": "<b>x"}])
    client = TestClient(api.app)
    page = client.get("/approvals").text
    assert "&lt;b&gt;x" in page and "me%2Ft%231%40a" in page  # escaped; key url-encoded
    bad = client.post("/approvals", params={"key": "me/t#1@a", "decision": "approve"},
                      headers={"Origin": "https://evil.example"})  # fmt: skip
    assert bad.status_code == 403
    q = {"key": "me/t#1@a", "decision": "approve"}
    assert client.post("/approvals", params=q, follow_redirects=False).status_code == 303
    assert client.post("/approvals", params=q).status_code == 404
