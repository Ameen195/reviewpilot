"""Reliable Redis list queue: jobs move to a processing list while running, so a killed
worker's job is recovered on restart. Plain redis instead of RQ: RQ's worker needs fork (no Windows).
"""

import json

import redis

from reviewpilot.config import get_settings

QUEUE, PROCESSING, PENDING = "rp:queue", "rp:processing", "rp:pending"
SEEN_TTL = 30 * 86400
BLOCK_TIMEOUT = 5  # seconds BLMOVE waits for a job
SOCKET_TIMEOUT = 30  # must be longer than BLOCK_TIMEOUT or idle waits time out client-side


def connect() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT
    )


def job_key(repo: str, number: int, sha: str) -> str:
    return f"{repo}#{number}@{sha}"  # also the checkpoint thread_id


def enqueue(r: redis.Redis, repo: str, number: int, sha: str) -> bool:
    """False if this head commit was already queued (GitHub redelivery, reopen, etc.)."""
    key = job_key(repo, number, sha)
    if not r.set(f"rp:seen:{key}", 1, nx=True, ex=SEEN_TTL):
        return False
    r.lpush(QUEUE, json.dumps({"key": key, "repo": repo, "number": number, "sha": sha}))
    return True


def forget(r: redis.Redis, key: str) -> None:
    """Allow a failed job's commit to be queued again."""
    r.delete(f"rp:seen:{key}")


def next_job(r: redis.Redis, timeout: int = BLOCK_TIMEOUT) -> str | None:
    """None when no job arrived in time, including a client-side socket timeout."""
    try:
        return r.blmove(QUEUE, PROCESSING, timeout, "RIGHT", "LEFT")
    except redis.TimeoutError:
        # the server may have moved a job just as we gave up; with one idle worker anything
        # in PROCESSING is orphaned, so put it back for the next call
        recover(r)
        return None


def done(r: redis.Redis, raw: str) -> None:
    r.lrem(PROCESSING, 1, raw)


def recover(r: redis.Redis) -> int:
    """Move jobs a killed worker left in PROCESSING back to the queue, oldest first."""
    # shortcut: assumes one worker; with several, track per-worker processing lists
    n = 0
    while r.lmove(PROCESSING, QUEUE, "RIGHT", "RIGHT"):
        n += 1
    return n


def add_pending(r: redis.Redis, job: dict, critical: list[dict]) -> None:
    r.hset(PENDING, job["key"], json.dumps({"job": job, "critical": critical}))


def list_pending(r: redis.Redis) -> dict[str, dict]:
    return {k: json.loads(v) for k, v in r.hgetall(PENDING).items()}


def decide(r: redis.Redis, key: str, decision: str) -> bool:
    """Queue a resume job. False if not pending (unknown key or already decided)."""
    raw = r.hget(PENDING, key)
    if raw is None or not r.hdel(PENDING, key):  # hdel is atomic: a double click resumes once
        return False
    r.lpush(QUEUE, json.dumps({**json.loads(raw)["job"], "resume": decision}))
    return True
