"""Read-only MCP server (stdio). Run: python -m reviewpilot.mcp_server

stdout carries the JSON-RPC stream, so everything we log goes to stderr.
No tool posts to GitHub; review_file spends Groq tokens, run_tests_sandboxed needs Docker.
"""

import logging
import re
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from reviewpilot.config import get_settings

mcp = MCPServer("reviewpilot")
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_REPO = re.compile(r"^[A-Za-z0-9][\w-]*/(?!\.{1,2}$)[\w.-]+$")
log = logging.getLogger("reviewpilot.mcp")


def _client(repo: str):
    """GitHub client for repo; refuses repos outside ALLOWED_REPOS or without the App installed."""
    if not _REPO.match(repo):
        raise ValueError("repo must look like owner/name")
    allowed = get_settings().allowed_repo_set
    if allowed and repo.lower() not in allowed:
        raise ValueError(f"{repo} is not in ALLOWED_REPOS")
    from github import GithubException

    from reviewpilot.github.auth import installation_client

    try:
        return installation_client(*repo.split("/"))
    except GithubException as e:
        raise ValueError(f"the GitHub App is not installed on {repo} ({e.status})") from e


def _context(repo: str, number: int):
    from reviewpilot.context.build import build_context
    from reviewpilot.github.pr import fetch_pr

    gh = _client(repo)
    return gh, build_context(*fetch_pr(gh, repo, number))


@mcp.tool(annotations=READ_ONLY)
def get_pr_context(repo: str, number: int) -> dict:
    """Changed files of a PR (owner/name, PR number): diffs plus files skipped and why."""
    _, ctx = _context(repo, number)
    return {
        "number": ctx.number, "title": ctx.title, "head_sha": ctx.head_sha, "tokens": ctx.tokens,
        "files": [{"path": f.path, "status": f.status, "patch": f.patch} for f in ctx.files],
        "skipped": [{"path": p, "reason": r} for p, r in ctx.skipped],
    }  # fmt: skip


@mcp.tool(annotations=READ_ONLY)
def review_file(repo: str, number: int, path: str) -> dict:
    """Run the three reviewers on one file of a PR. Uses Groq tokens. Does not run tests or post."""
    from reviewpilot.agents.graph import review

    _, ctx = _context(repo, number)
    ctx.files = [f for f in ctx.files if f.path == path]
    if not ctx.files:
        raise ValueError(f"{path} is not a reviewable changed file in {repo}#{number}")
    out = review(ctx)
    return {
        "inline": [f.model_dump() for f in out["inline"]],
        "summary": [f.model_dump() for f in out["summary"]],
        "tokens": out["tokens"], "errors": out.get("errors", []),
    }  # fmt: skip


@mcp.tool(annotations=READ_ONLY)
def run_tests_sandboxed(repo: str, number: int) -> dict:
    """Run the PR head's tests in the locked-down Docker sandbox (no network). Needs Docker."""
    from reviewpilot.sandbox.runner import sandbox_pr

    gh = _client(repo)
    sha = gh.get_repo(repo).get_pull(number).head.sha
    r = sandbox_pr(gh, repo, sha)
    return {"head_sha": sha, "passed": r.passed, "failed": r.failed,
            "timed_out": r.timed_out, "error": r.error}  # fmt: skip


@mcp.tool(annotations=READ_ONLY)
def list_findings(repo: str, number: int) -> dict:
    """Findings from the stored review of the PR's current head commit; never calls the LLM."""
    from reviewpilot.agents.graph import checkpointer
    from reviewpilot.queue.jobs import job_key

    gh = _client(repo)
    sha = gh.get_repo(repo).get_pull(number).head.sha
    db = get_settings().checkpoint_db
    if not Path(db).exists():
        return {"head_sha": sha, "reviewed": False, "inline": [], "summary": []}
    tup = checkpointer(db).get_tuple({"configurable": {"thread_id": job_key(repo, number, sha)}})
    vals = tup.checkpoint["channel_values"] if tup else {}
    if "inline" not in vals:  # never reviewed, or still paused before the filter step
        return {"head_sha": sha, "reviewed": False, "inline": [], "summary": []}
    return {
        "head_sha": sha, "reviewed": True,
        "posted": bool(vals.get("posted")),  # False while paused for approval
        "inline": [f.model_dump() for f in vals["inline"]],
        "summary": [f.model_dump() for f in vals["summary"]],
    }  # fmt: skip


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, force=True)
    log.info("reviewpilot MCP server starting (stdio)")
    mcp.run("stdio")
