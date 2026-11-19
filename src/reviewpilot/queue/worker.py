"""Worker: python -m reviewpilot.queue.worker"""

import json
import logging
from collections.abc import Callable

from langgraph.types import Command

from reviewpilot.agents.graph import build_graph, checkpointer
from reviewpilot.agents.llm import chat_json
from reviewpilot.config import get_settings
from reviewpilot.queue import jobs

log = logging.getLogger("reviewpilot.worker")


def live_setup(job: dict):
    """-> (ctx, run_tests, post) for a job, talking to GitHub."""
    from reviewpilot.context.build import build_context
    from reviewpilot.github.auth import installation_client
    from reviewpilot.github.post import post_review
    from reviewpilot.github.pr import fetch_pr
    from reviewpilot.sandbox.runner import sandbox_pr

    repo = job["repo"]
    gh = installation_client(*repo.split("/"))
    ctx = build_context(*fetch_pr(gh, repo, job["number"]))
    return (
        ctx,
        lambda c: sandbox_pr(gh, repo, c.head_sha),
        lambda state: post_review(gh, repo, ctx, state),
    )


def process(r, raw: str, saver, setup: Callable = live_setup, llm: Callable = chat_json) -> str:
    """Run, resume or skip one job. Returns what happened (for logs and tests)."""
    job = json.loads(raw)
    key = job["key"]
    ctx, run_tests, post = setup(job)
    if ctx.head_sha != job["sha"]:  # PR moved on; the newer push has its own job
        return "stale"
    graph = build_graph(ctx, llm, run_tests, post, saver)
    config = {"configurable": {"thread_id": key}}
    snap = graph.get_state(config)
    if "resume" in job:
        if snap.next != ("approve",):
            return "not-waiting"
        log.info("%s: human said %s", key, job["resume"])
        graph.invoke(Command(resume=job["resume"]), config)
    elif snap.next == ("approve",):
        pass  # paused already (worker died before listing it): re-list below, hset is idempotent
    elif snap.next:
        log.info("%s: resuming from checkpoint at %s", key, snap.next)
        graph.invoke(None, config)
    elif snap.values:
        return "already-done"
    else:
        log.info("%s: starting review", key)
        graph.invoke({}, config)
    snap = graph.get_state(config)
    if snap.next == ("approve",):
        critical = snap.tasks[0].interrupts[0].value["critical"]
        jobs.add_pending(r, {k: v for k, v in job.items() if k != "resume"}, critical)
        log.info("%s: %d critical finding(s) wait for approval", key, len(critical))
        return "paused"
    log.info("%s: done, posted=%s tokens=%s", key, snap.values.get("posted"),
             snap.values.get("tokens"))  # fmt: skip
    return "posted" if snap.values.get("posted") else "duplicate"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    r = jobs.connect()
    saver = checkpointer(get_settings().checkpoint_db)
    if n := jobs.recover(r):
        log.info("recovered %d unfinished job(s)", n)
    log.info("worker ready")
    while True:
        raw = jobs.next_job(r)
        if raw is None:
            continue
        try:
            process(r, raw, saver)
        except Exception:  # a bad job must not stop the worker
            log.exception("job failed: %s", raw)
            jobs.forget(r, json.loads(raw)["key"])
        jobs.done(r, raw)


if __name__ == "__main__":
    main()
