import logging
import operator
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field, ValidationError

from reviewpilot.agents.llm import chat_json
from reviewpilot.agents.prompts import system_prompt, user_prompt
from reviewpilot.context.build import PRContext
from reviewpilot.sandbox.runner import SandboxResult

log = logging.getLogger(__name__)

# Two models so the per-model Groq limits are spread out.
REVIEWERS = {
    "bug": "openai/gpt-oss-120b",
    "security": "openai/gpt-oss-120b",
    "tests": "openai/gpt-oss-20b",
}
TIE_ORDER = ["security", "bug", "tests"]  # same line: the most specific reviewer wins
MIN_CONFIDENCE = 0.6
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


class Finding(BaseModel):
    file: str
    line: int | None = None
    severity: Literal["low", "medium", "high", "critical"]
    category: str
    message: str
    suggested_fix: str = ""
    confidence: float = Field(ge=0, le=1)
    bumped_by_tests: bool = False  # severity raised one level by a failing test near the change


class State(TypedDict, total=False):
    # Checkpointed, so small values only: PRContext does not round-trip (tuples become lists);
    # it is passed to the nodes by closure and rebuilt from GitHub for the same head sha.
    tests: SandboxResult | None  # None when the sandbox is not used
    raw: Annotated[list[Finding], operator.add]
    tokens: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]
    merged: list[Finding]
    inline: list[Finding]  # tied to a commentable changed line
    summary: list[Finding]  # PR-level: no line, or a line that cannot take a comment
    rejected: int  # critical findings a human rejected
    posted: bool


def _reviewer(name: str, model: str, llm: Callable, ctx: PRContext):
    def run(state: State) -> State:
        found, tokens, errors = [], 0, []
        paths = [f.path for f in ctx.files]
        for f in ctx.files:
            if name == "tests" and is_test_file(f.path):
                continue  # tests are what this reviewer looks for, not what it reviews
            others = [p for p in paths if p != f.path]
            # the tests reviewer must see the PR's tests for this file, not just their names
            related = [t for t in ctx.files if name == "tests" and
                       PurePosixPath(t.path).name in tests_for(f.path)]  # fmt: skip
            try:
                prompt = user_prompt(ctx.title, f, others, state.get("tests"), related)
                data, used = llm(model, system_prompt(name), prompt)
            except Exception as e:  # noqa: BLE001 - one failed call must not sink the whole review
                errors.append(f"{name} {f.path}: {e}")
                continue
            tokens += used
            items = data.get("findings") if isinstance(data, dict) else None
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                try:  # file/category come from us, not the model
                    found.append(Finding(**{**item, "file": f.path, "category": name}))
                except (ValidationError, TypeError) as e:
                    errors.append(f"{name} {f.path}: bad finding dropped ({e.__class__.__name__})")
        return {"raw": found, "tokens": tokens, "errors": errors}

    return run


def merge(state: State) -> State:
    """Same file and same line -> one finding; the specialist wins, then the most confident.

    Low-confidence findings are dropped first so they cannot displace a confident one.
    """
    kept: dict[tuple[str, int], Finding] = {}
    pr_level: list[Finding] = []
    rank = lambda f: (TIE_ORDER.index(f.category), -f.confidence)
    for f in sorted(state.get("raw", []), key=rank):
        if f.confidence < MIN_CONFIDENCE:
            continue
        if f.line is None or f.category == "tests":
            pr_level.append(f)
        else:
            kept.setdefault((f.file, f.line), f)
    return {"merged": [*kept.values(), *pr_level]}


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.startswith("test_") or name.endswith("_test.py")


def tests_for(path: str) -> set[str]:
    """File names of the tests that cover `path`: test_<stem>.py and <stem>_test.py."""
    stem = PurePosixPath(path).stem
    return {f"test_{stem}.py", f"{stem}_test.py"}


def failing_test_touches(path: str, failed: list[str]) -> bool:
    """A failing test lives in test_<stem>.py / <stem>_test.py of this source file.

    Never true for a test file itself: its failure is evidence about the code it tests.
    """
    if is_test_file(path):
        return False
    names = tests_for(path)
    return any(PurePosixPath(t.split(" ")[0].split("::")[0]).name in names for t in failed)


def _bump(f: Finding) -> Finding:
    i = SEVERITY_ORDER.index(f.severity)
    return f.model_copy(update={"severity": SEVERITY_ORDER[max(i - 1, 0)], "bumped_by_tests": True})


def filter_findings(state: State, ctx: PRContext) -> State:
    diffs = {f.path: f.diff for f in ctx.files}
    tests = state.get("tests")
    failed = tests.failed if tests and not tests.error else []
    inline, summary = [], []
    code = [f for f in state["merged"] if f.category != "tests"]
    covered = {n for f in code if not is_test_file(f.file) for n in tests_for(f.file)}
    for f in state["merged"]:
        if f in code and PurePosixPath(f.file).name in covered:
            continue  # restates a bug already reported on the code this test file covers
        if f.category != "tests" and failing_test_touches(f.file, failed):
            f = _bump(f)
        if f.category != "tests" and f.line is not None and diffs[f.file].can_comment(f.line):
            inline.append(f)
        else:
            summary.append(f)
    key = lambda f: (SEVERITY_ORDER.index(f.severity), f.file, f.line or 0)
    return {"inline": sorted(inline, key=key), "summary": sorted(summary, key=key)}


def approve(state: State) -> State:
    """Critical findings wait for a human. The resume value is "approve" or "reject"."""
    critical = [f for f in state["inline"] + state["summary"] if f.severity == "critical"]
    if not critical:
        return {}
    decision = interrupt({"critical": [f.model_dump() for f in critical]})
    if decision == "approve":
        return {}
    keep = lambda fs: [f for f in fs if f.severity != "critical"]
    return {"inline": keep(state["inline"]), "summary": keep(state["summary"]),
            "rejected": len(critical)}  # fmt: skip


def checkpointer(path: str) -> SqliteSaver:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("reviewpilot.agents.graph", "Finding"), ("reviewpilot.sandbox.runner", "SandboxResult"),
    ])  # fmt: skip
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False), serde=serde)


def build_graph(
    ctx: PRContext,
    llm: Callable = chat_json,
    run_tests: Callable | None = None,
    post: Callable[[State], bool] | None = None,
    saver: SqliteSaver | None = None,
):
    """With `post`, critical findings pause for approval (needs `saver`), then post(state) runs."""
    g = StateGraph(State)
    g.add_node("sandbox", lambda s: {"tests": run_tests(ctx) if run_tests else None})
    g.add_edge(START, "sandbox")
    for name, model in REVIEWERS.items():
        g.add_node(name, _reviewer(name, model, llm, ctx))
        g.add_edge("sandbox", name)
        g.add_edge(name, "merge")
    g.add_node("merge", merge)
    g.add_node("filter", lambda s: filter_findings(s, ctx))
    g.add_edge("merge", "filter")
    if post:
        g.add_node("approve", approve)
        g.add_node("post", lambda s: {"posted": post(s)})
        g.add_edge("filter", "approve")
        g.add_edge("approve", "post")
        g.add_edge("post", END)
    else:
        g.add_edge("filter", END)
    return g.compile(checkpointer=saver)


def review(ctx: PRContext, llm: Callable = chat_json, run_tests: Callable | None = None) -> State:
    """Print-only review, nothing posted. run_tests(ctx) -> SandboxResult; omit to skip tests."""
    return build_graph(ctx, llm, run_tests).invoke({})


def main(argv: list[str]) -> None:
    """Live run, prints only: python -m reviewpilot.agents.graph owner/repo 12"""
    from reviewpilot.agents.prompts import format_tests
    from reviewpilot.context.build import build_context
    from reviewpilot.github.auth import installation_client
    from reviewpilot.github.pr import fetch_pr
    from reviewpilot.sandbox.runner import sandbox_pr

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows console is cp1252
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    full_name, number = argv[0], int(argv[1])
    owner, repo = full_name.split("/")
    gh = installation_client(owner, repo)
    ctx = build_context(*fetch_pr(gh, full_name, number))
    out = review(ctx, run_tests=lambda c: sandbox_pr(gh, full_name, c.head_sha))
    print(
        f"\nPR #{ctx.number} head={ctx.head_sha[:7]} files={len(ctx.files)} "
        f"tokens_used={out['tokens']}"
    )
    print("Tests: " + format_tests(out["tests"]).replace("\n", "\n  "))
    for title, items in (("Inline", out["inline"]), ("Summary", out["summary"])):
        print(f"\n{title} findings ({len(items)}):")
        for f in items:
            where = f"{f.file}:{f.line}" if f.line else f.file
            bumped = " (raised by failing test)" if f.bumped_by_tests else ""
            print(f"  [{f.severity}]{bumped} {f.category} {where} (conf {f.confidence:.2f})")
            print(f"      {f.message}")
            if f.suggested_fix:
                print(f"      fix: {f.suggested_fix}")
    for e in out.get("errors", []):
        print(f"  error: {e}")
    for path, reason in ctx.skipped:
        print(f"  skipped {path}: {reason}")


if __name__ == "__main__":
    main(sys.argv[1:])
