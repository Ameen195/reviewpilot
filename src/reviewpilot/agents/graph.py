import logging
import operator
import sys
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
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


class State(TypedDict, total=False):
    ctx: PRContext
    tests: SandboxResult | None  # None when the sandbox is not used
    raw: Annotated[list[Finding], operator.add]
    tokens: Annotated[int, operator.add]
    errors: Annotated[list[str], operator.add]
    merged: list[Finding]
    inline: list[Finding]  # tied to a commentable changed line
    summary: list[Finding]  # PR-level: no line, or a line that cannot take a comment


def _reviewer(name: str, model: str, llm: Callable):
    def run(state: State) -> State:
        ctx, found, tokens, errors = state["ctx"], [], 0, []
        paths = [f.path for f in ctx.files]
        for f in ctx.files:
            others = [p for p in paths if p != f.path]
            try:
                prompt = user_prompt(ctx.title, f, others, state.get("tests"))
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


def failing_test_touches(path: str, failed: list[str]) -> bool:
    """A failing test lives in this file, or in test_<stem>.py / <stem>_test.py."""
    p = PurePosixPath(path)
    names = {p.name, f"test_{p.stem}.py", f"{p.stem}_test.py"}
    return any(PurePosixPath(t.split(" ")[0].split("::")[0]).name in names for t in failed)


def _bump(f: Finding) -> Finding:
    i = SEVERITY_ORDER.index(f.severity)
    return f.model_copy(update={"severity": SEVERITY_ORDER[max(i - 1, 0)]})


def filter_findings(state: State) -> State:
    diffs = {f.path: f.diff for f in state["ctx"].files}
    tests = state.get("tests")
    failed = tests.failed if tests and not tests.error else []
    inline, summary = [], []
    for f in state["merged"]:
        if f.category != "tests" and failing_test_touches(f.file, failed):
            f = _bump(f)
        if f.category != "tests" and f.line is not None and diffs[f.file].can_comment(f.line):
            inline.append(f)
        else:
            summary.append(f)
    key = lambda f: (SEVERITY_ORDER.index(f.severity), f.file, f.line or 0)
    return {"inline": sorted(inline, key=key), "summary": sorted(summary, key=key)}


def build_graph(llm: Callable = chat_json, run_tests: Callable | None = None):
    g = StateGraph(State)
    g.add_node("sandbox", lambda s: {"tests": run_tests(s["ctx"]) if run_tests else None})
    g.add_edge(START, "sandbox")
    for name, model in REVIEWERS.items():
        g.add_node(name, _reviewer(name, model, llm))
        g.add_edge("sandbox", name)
        g.add_edge(name, "merge")
    g.add_node("merge", merge)
    g.add_node("filter", filter_findings)
    g.add_edge("merge", "filter")
    g.add_edge("filter", END)
    return g.compile()


def review(ctx: PRContext, llm: Callable = chat_json, run_tests: Callable | None = None) -> State:
    """run_tests(ctx) -> SandboxResult; omit it to review without running tests."""
    return build_graph(llm, run_tests).invoke({"ctx": ctx})


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
            print(f"  [{f.severity}] {f.category} {where} (conf {f.confidence:.2f})")
            print(f"      {f.message}")
            if f.suggested_fix:
                print(f"      fix: {f.suggested_fix}")
    for e in out.get("errors", []):
        print(f"  error: {e}")
    for path, reason in ctx.skipped:
        print(f"  skipped {path}: {reason}")


if __name__ == "__main__":
    main(sys.argv[1:])
