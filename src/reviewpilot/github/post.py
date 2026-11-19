"""Post one review: inline comments + a summary body. The only write action ReviewPilot has."""

from reviewpilot.agents.prompts import format_tests
from reviewpilot.context.build import PRContext

MARKER = "<!-- reviewpilot:{sha} -->"  # idempotency key per head commit, hidden in the body


def finding_text(f) -> str:
    bumped = " (severity raised: failing test near this change)" if f.bumped_by_tests else ""
    text = f"**[{f.severity}] {f.category}**{bumped}: {f.message}"
    return text + (f"\n\nSuggested fix: {f.suggested_fix}" if f.suggested_fix else "")


def summary_body(ctx: PRContext, state: dict) -> str:
    inline, summary = state.get("inline", []), state.get("summary", [])
    lines = [
        "## ReviewPilot review",
        f"{len(inline)} inline comment(s), {len(summary)} PR-level finding(s).",
    ]
    if state.get("tests"):
        lines.append("Tests: " + format_tests(state["tests"]).splitlines()[0])
    if state.get("rejected"):
        lines.append(f"{state['rejected']} critical finding(s) were rejected by a human reviewer.")
    for f in summary:
        where = f"`{f.file}:{f.line}`" if f.line else f"`{f.file}`"
        lines.append(f"- {where} {finding_text(f)}")
    if ctx.skipped:
        lines.append("Skipped: " + ", ".join(f"`{p}` ({why})" for p, why in ctx.skipped))
    lines.append(MARKER.format(sha=ctx.head_sha))
    return "\n\n".join(lines)


def post_review(gh, full_name: str, ctx: PRContext, state: dict) -> bool:
    """Returns False if this head commit was already reviewed (crash after post, before checkpoint)."""
    repo = gh.get_repo(full_name)
    pr = repo.get_pull(ctx.number)
    marker = MARKER.format(sha=ctx.head_sha)
    if any(marker in (r.body or "") for r in pr.get_reviews()):
        return False
    comments = [
        {"path": f.file, "line": f.line, "side": "RIGHT", "body": finding_text(f)}
        for f in state.get("inline", [])
    ]
    pr.create_review(  # one call: inline comments and summary land together or not at all
        commit=repo.get_commit(ctx.head_sha),
        body=summary_body(ctx, state),
        event="COMMENT",  # never APPROVE or REQUEST_CHANGES
        comments=comments,
    )
    return True
