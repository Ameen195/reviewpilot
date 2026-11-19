"""Run the planted-bug eval, one PR at a time, resumable across days.

    uv run python eval/run.py --limit 3     # trial
    uv run python eval/run.py               # everything not done yet

One result file per PR in eval/results/prs/. A PR with a result for the current git commit (and
unchanged PR content) is skipped; results from another commit are ignored unless --any-commit.
LLM replies are cached in data/cache, so re-running a PR whose prompts did not change costs 0.
Stops cleanly on a Groq rate-limit error or when today's tokens per model near --daily-guard.
"""

import argparse
import datetime
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import groq
import plant

from reviewpilot.agents.graph import REVIEWERS, review
from reviewpilot.agents.llm import chat_json
from reviewpilot.context.build import build_context
from reviewpilot.sandbox.runner import run_tests

RESULTS = Path(__file__).parent / "results"
PRS_DIR = RESULTS / "prs"
USAGE = RESULTS / "usage.json"  # {date: {model: tokens}} for the daily guard
PR_MARGIN = 15_000  # never start a PR with less than this left under the guard


def git_commit() -> tuple[str, bool]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=False, capture_output=True, text=True
    ).stdout
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], check=False, capture_output=True, text=True
    ).stdout
    return sha.strip(), bool(dirty.strip())


def pr_hash(files: list[dict]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]


def load_result(pr_id: str, commit: str, phash: str, any_commit: bool) -> dict | None:
    path = PRS_DIR / f"{pr_id}.json"
    if not path.exists():
        return None
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("pr_hash") != phash or (r.get("commit") != commit and not any_commit):
        return None
    return r


class RateLimited(Exception):
    pass


def run_one(pr: dict) -> dict:
    head, files, contents = plant.build(pr)
    ctx = build_context(head, files, lambda p: contents.get(p))
    by_model: dict[str, int] = {}
    llm_s = 0.0
    limited: list[Exception] = []

    def llm(model, system, user):
        nonlocal llm_s
        t = time.perf_counter()
        try:
            data, used = chat_json(model, system, user)
        except (groq.RateLimitError, groq.APIConnectionError) as e:
            limited.append(e)
            raise
        finally:
            llm_s += time.perf_counter() - t
        by_model[model] = by_model.get(model, 0) + used
        return data, used

    def sandbox(_ctx):
        with tempfile.TemporaryDirectory(prefix="rp-eval-") as tmp:
            src = Path(tmp) / "repo"
            shutil.copytree(plant.REPO, src, ignore=shutil.ignore_patterns("__pycache__"))
            for path, text in contents.items():
                (src / path).parent.mkdir(parents=True, exist_ok=True)
                (src / path).write_text(text, encoding="utf-8")
            return run_tests(src)

    t = time.perf_counter()
    out = review(ctx, llm=llm, run_tests=sandbox)
    latency = time.perf_counter() - t
    if limited:  # a partial review would skew the numbers; retry this PR later
        raise RateLimited(str(limited[0])[:300])
    tests = out.get("tests")
    return {
        "tokens": out.get("tokens", 0), "tokens_by_model": by_model,
        "latency_s": round(latency, 2), "llm_s": round(llm_s, 2),
        "tests": tests and {"passed": tests.passed, "failed": tests.failed, "error": tests.error},
        "inline": [f.model_dump() for f in out.get("inline", [])],
        "summary": [f.model_dump() for f in out.get("summary", [])],
        "errors": out.get("errors", []), "skipped": ctx.skipped,
    }  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="run at most this many new PRs")
    ap.add_argument("--daily-guard", type=int, default=180_000, help="tokens per model per day")
    ap.add_argument("--any-commit", action="store_true", help="accept results from other commits")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    commit, dirty = git_commit()
    PRS_DIR.mkdir(parents=True, exist_ok=True)
    usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}
    today = datetime.date.today().isoformat()
    used = usage.setdefault(today, {})
    ran = 0
    for pr in plant.ORDER:
        _, files, _ = plant.build(pr)
        phash = pr_hash(files)
        if load_result(pr["id"], commit, phash, args.any_commit):
            continue
        if args.limit is not None and ran >= args.limit:
            break
        near = [m for m in set(REVIEWERS.values()) if used.get(m, 0) + PR_MARGIN > args.daily_guard]
        if near:
            print(f"stop: daily guard reached for {near}; run again tomorrow")
            break
        try:
            r = run_one(pr)
        except RateLimited as e:
            print(f"stop: Groq rate limit on {pr['id']} ({e}); run again later")
            break
        for m, n in r["tokens_by_model"].items():
            used[m] = used.get(m, 0) + n
        USAGE.write_text(json.dumps(usage, indent=1))
        r = {"id": pr["id"], "commit": commit, "dirty": dirty, "pr_hash": phash,
             "date": today, **r}  # fmt: skip
        (PRS_DIR / f"{pr['id']}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
        ran += 1
        t = r["tests"] or {}
        print(
            f"{pr['id']:>4} tokens={r['tokens']:>5} {r['latency_s']:>6.1f}s "
            f"inline={len(r['inline'])} summary={len(r['summary'])} "
            f"tests={t.get('passed')}p/{len(t.get('failed') or [])}f errors={len(r['errors'])}"
        )
    done = sum(load_result(p["id"], commit, pr_hash(plant.build(p)[1]), args.any_commit)
               is not None for p in plant.ORDER)  # fmt: skip
    print(
        f"ran {ran} now; {done}/{len(plant.ORDER)} done for commit {commit[:7]}"
        f"{' (dirty tree)' if dirty else ''}; tokens today: {used}"
    )


if __name__ == "__main__":
    main()
