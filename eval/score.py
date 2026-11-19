"""Score eval results (offline, no LLM calls).

    uv run python eval/score.py [--any-commit] [--set heldout] [--results eval/results/after]

Writes <results>/summary.json and summary.md (summary_<set>.* for other sets). Definitions:
- hit: a code finding (bug/security reviewer) in the planted file within +/-2 lines of the planted
  line. For a missing_test PR, a hit is a tests-reviewer finding on the planted file.
- category accuracy: of the detected bugs, how many had a hit from the expected reviewer
  (findings only carry the reviewer name: bug, security or tests).
- code false positive: a code finding that is not a hit, not a duplicate and not a test-file echo.
  "Missing tests" notes (tests reviewer) are counted separately and never as false positives.
- duplicate: every hit after the first one on the same planted bug.
- test-file echo: a code finding on a test file in a bug PR (the planted bug's test failing,
  reported again on the test file itself).
- misplaced summary: a code hit that landed in the summary instead of an inline comment.

Human verdicts in <results>/manual_review.json (if present) correct ambiguous line matches; both raw and corrected
numbers are reported, corrected is the headline:
- "unrelated": hits that describe a different issue; they stop counting as a hit and count as a
  code false positive instead.
- "not_duplicate": hits that are a separate real bug (e.g. a second planted secret); they stay
  hits but are not counted as duplicates.
Token and latency stats skip PRs answered fully from the LLM cache (0 tokens).
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

import plant
from run import RESULTS, git_commit, load_result, pr_hash

from reviewpilot.agents.graph import is_test_file

LINE_TOLERANCE = 2


def _key(f: dict) -> tuple:
    return f["file"], f["line"], f["category"]


def score_pr(truth: dict, result: dict, review: dict | None = None) -> dict:
    """truth: a dataset row. result: a results/prs file. review: its manual_review.json entry."""
    review = review or {}
    unrelated = {_key(f) for f in review.get("unrelated", [])}
    not_dup = {_key(f) for f in review.get("not_duplicate", [])}
    findings = [(f, "inline") for f in result["inline"]] + [
        (f, "summary") for f in result["summary"]
    ]
    clean = truth["category"] == "clean"

    def hit(f: dict) -> bool:
        if clean or f["file"] != truth["file"] or _key(f) in unrelated:
            return False
        if truth["category"] == "missing_test":
            return f["category"] == "tests"
        return f["category"] != "tests" and f["line"] is not None and \
            abs(f["line"] - truth["line"]) <= LINE_TOLERANCE  # fmt: skip

    hits = [(f, where) for f, where in findings if hit(f)]
    rest = [(f, where) for f, where in findings if not hit(f)]
    code = [(f, where) for f, where in rest if f["category"] != "tests"]
    echoes = [f for f, _ in code if not clean and is_test_file(f["file"])]
    return {
        "id": truth["id"], "category": truth["category"],
        "detected": bool(hits),
        "category_ok": any(f["category"] == truth["expected_reviewer"] for f, _ in hits),
        "duplicates": max(len(hits) - 1 - sum(_key(f) in not_dup for f, _ in hits), 0),
        "echoes": len(echoes),
        "echoes_bumped": sum(f.get("bumped_by_tests", False) for f in echoes),
        "code_fp": len(code) - len(echoes),
        "missing_tests_notes": sum(f["category"] == "tests" for f, _ in rest),
        "misplaced_summary": sum(where == "summary" and f["category"] != "tests" for f, where in hits),
        "summary_code_findings": sum(where == "summary" for f, where in code + hits
                                     if f["category"] != "tests"),
        "tokens": result["tokens"], "latency_s": result["latency_s"],
        "errors": len(result["errors"]),
    }  # fmt: skip


def p95(xs: list[float]) -> float:
    return sorted(xs)[max(round(0.95 * len(xs)) - 1, 0)] if xs else 0.0


def rate(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def aggregate(rows: list[dict], total: int) -> dict:
    bug = [r for r in rows if r["category"] != "clean"]
    clean = [r for r in rows if r["category"] == "clean"]
    det = [r for r in bug if r["detected"]]
    per_pr = lambda rs, k: round(sum(r[k] for r in rs) / len(rs), 2) if rs else None
    cats = {}
    for c in dict.fromkeys(r["category"] for r in bug):
        rs = [r for r in bug if r["category"] == c]
        d = [r for r in rs if r["detected"]]
        cats[c] = {"prs": len(rs), "detected": len(d), "detection_rate": rate(len(d), len(rs)),
                   "category_ok": sum(r["category_ok"] for r in d),
                   "category_accuracy": rate(sum(r["category_ok"] for r in d), len(d)),
                   "code_fp_per_pr": per_pr(rs, "code_fp")}  # fmt: skip
    real = [r for r in rows if r["tokens"] > 0]  # fully cached PRs would skew cost and speed
    tok = [r["tokens"] for r in real]
    lat = [r["latency_s"] for r in real]
    return {
        "prs_scored": len(rows), "prs_total": total, "bug_prs": len(bug), "clean_prs": len(clean),
        "detection_rate": rate(len(det), len(bug)),
        "category_accuracy": rate(sum(r["category_ok"] for r in det), len(det)),
        "code_fp_per_pr": {"bug_prs": per_pr(bug, "code_fp"), "clean_prs": per_pr(clean, "code_fp")},
        "missing_tests_notes_per_pr": {"bug_prs": per_pr(bug, "missing_tests_notes"),
                                       "clean_prs": per_pr(clean, "missing_tests_notes")},
        "known_issues": {
            "duplicates": sum(r["duplicates"] for r in rows),
            "prs_with_duplicates": sum(r["duplicates"] > 0 for r in rows),
            "test_file_echoes": sum(r["echoes"] for r in rows),
            "test_file_echoes_bumped": sum(r["echoes_bumped"] for r in rows),
            "prs_with_echoes": sum(r["echoes"] > 0 for r in rows),
            "summary_code_findings": sum(r["summary_code_findings"] for r in rows),
            "misplaced_summary_hits": sum(r["misplaced_summary"] for r in rows),
        },
        "by_category": cats,
        "prs_with_real_tokens": len(real),
        "tokens_per_pr": {"mean": round(statistics.mean(tok)) if tok else 0, "p95": p95(tok),
                          "total": sum(tok)},
        "latency_s_per_pr": {"mean": round(statistics.mean(lat), 1) if lat else 0.0,
                             "p95": p95(lat)},
        "prs_with_errors": sum(r["errors"] > 0 for r in rows),
    }  # fmt: skip


def to_markdown(s: dict, commit: str, name: str = "original") -> str:
    k = s["known_issues"]
    lines = [
        f"# Eval summary, {name} set, corrected (commit {commit[:7]}, {s['prs_scored']}/{s['prs_total']} PRs scored)", "",
        f"- Detection rate: {s['detection_rate']} ({s['bug_prs']} bug PRs, +/-{LINE_TOLERANCE} lines)",
        f"- Category accuracy (detected bugs, right reviewer): {s['category_accuracy']}",
        (f"- Code false positives per PR: bug PRs {s['code_fp_per_pr']['bug_prs']}, "
        f"clean PRs {s['code_fp_per_pr']['clean_prs']}"),
        (f"- Missing-tests notes per PR (separate): bug PRs "
        f"{s['missing_tests_notes_per_pr']['bug_prs']}, "
        f"clean PRs {s['missing_tests_notes_per_pr']['clean_prs']}"),
        (f"- Duplicates: {k['duplicates']} in {k['prs_with_duplicates']} PRs; test-file echoes: "
        f"{k['test_file_echoes']} in {k['prs_with_echoes']} PRs ({k['test_file_echoes_bumped']} bumped)"),
        (f"- Code findings in summary: {k['summary_code_findings']} "
        f"(of which real bugs that should be inline: {k['misplaced_summary_hits']})"),
        (f"- Tokens per PR ({s['prs_with_real_tokens']} PRs not fully cached): mean {s['tokens_per_pr']['mean']}, p95 {s['tokens_per_pr']['p95']}, "
        f"total {s['tokens_per_pr']['total']}"),
        f"- Latency per PR: mean {s['latency_s_per_pr']['mean']}s, p95 {s['latency_s_per_pr']['p95']}s",
        f"- PRs with reviewer errors: {s['prs_with_errors']}", "",
        "| Category | PRs | Detected | Rate | Right reviewer | Code FP/PR |", "|---|---|---|---|---|---|",
    ]  # fmt: skip
    for c, v in s["by_category"].items():
        lines.append(
            f"| {c} | {v['prs']} | {v['detected']} | {v['detection_rate']} | "
            f"{v['category_ok']}/{v['detected']} | {v['code_fp_per_pr']} |"
        )
    return "\n".join(lines) + "\n"


def stale_verdicts(manual: dict, results: dict[str, dict]) -> list[str]:
    """Verdicts naming a finding that is not in the result (e.g. after a re-run)."""
    out = []
    for pr_id, entry in manual.items():
        r = results.get(pr_id)
        found = {_key(f) for f in r["inline"] + r["summary"]} if r else set()
        for kind in ("unrelated", "not_duplicate"):
            out += [
                f"{pr_id} {kind} {_key(f)}" for f in entry.get(kind, []) if _key(f) not in found
            ]
    return out


def raw_vs_corrected(raw: dict, s: dict, manual: dict) -> str:
    rows = [
        ("Detection rate", raw["detection_rate"], s["detection_rate"]),
        ("Category accuracy", raw["category_accuracy"], s["category_accuracy"]),
        ("Code FP/PR, bug PRs", raw["code_fp_per_pr"]["bug_prs"], s["code_fp_per_pr"]["bug_prs"]),
        (
            "Code FP/PR, clean PRs",
            raw["code_fp_per_pr"]["clean_prs"],
            s["code_fp_per_pr"]["clean_prs"],
        ),
        ("Duplicates", raw["known_issues"]["duplicates"], s["known_issues"]["duplicates"]),
    ]
    lines = [
        "",
        f"## Raw vs corrected (manual review of {', '.join(manual)})",
        "",
        "| Metric | Raw | Corrected |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {a} | {b} |" for name, a, b in rows]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--any-commit", action="store_true", help="accept results from other commits")
    ap.add_argument("--set", choices=list(plant.SETS), default="original")
    ap.add_argument("--results", default=str(RESULTS), help="results dir (with prs/ inside)")
    args = ap.parse_args()
    res_dir, any_commit = Path(args.results), args.any_commit
    commit, _ = git_commit()
    manual_path = res_dir / "manual_review.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    manual = {k: v for k, v in manual.items() if not k.startswith("_")}
    truths, results = [], {}
    for truth in plant.dataset(args.set):
        r = load_result(truth["id"], commit, pr_hash(truth["files"]), any_commit, res_dir)
        if r:
            truths.append(truth)
            results[truth["id"]] = r
    manual = {k: v for k, v in manual.items() if k in {t["id"] for t in plant.dataset(args.set)}}
    if stale := stale_verdicts(manual, results):
        sys.exit(
            "manual_review.json does not match the results, update it:\n  " + "\n  ".join(stale)
        )
    raw_rows = [score_pr(t, results[t["id"]]) for t in truths]
    rows = [score_pr(t, results[t["id"]], manual.get(t["id"])) for t in truths]
    total = len(plant.SETS[args.set])
    raw, s = aggregate(raw_rows, total), aggregate(rows, total)
    result_commits = sorted({r["commit"][:7] for r in results.values()})
    out = {"commit": commit, "result_commits": result_commits, **s, "raw": raw, "per_pr": rows}
    stem = "summary" if args.set == "original" else f"summary_{args.set}"
    (res_dir / f"{stem}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    md = to_markdown(s, commit, args.set)
    md += raw_vs_corrected(raw, s, manual) if manual else "\nNo manual review for these results.\n"
    md += f"\nResult files were produced at commit(s): {', '.join(result_commits)}\n"
    (res_dir / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
