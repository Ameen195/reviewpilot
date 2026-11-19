import subprocess
import sys

import plant
from score import aggregate, score_pr

from reviewpilot.context.diff import parse_patch


def F(file, line, category="bug", **kw):
    return {"file": file, "line": line, "category": category, "severity": "high", **kw}


def result(inline=(), summary=()):
    return {"inline": list(inline), "summary": list(summary), "tokens": 100, "latency_s": 1.0,
            "errors": []}  # fmt: skip


TRUTH = {"id": "x", "category": "off_by_one", "expected_reviewer": "bug", "file": "shop/a.py",
         "line": 10}  # fmt: skip


def test_dataset_sane():
    rows = plant.dataset()
    assert len({r["id"] for r in rows}) == len(rows) == 50
    assert sum(r["category"] == "clean" for r in rows) == 10
    for r in rows:
        if r["category"] == "clean":
            assert r["line"] is None
            continue
        patch = next(f["patch"] for f in r["files"] if f["filename"] == r["file"])
        assert r["line"] in parse_patch(patch).added, r["id"]  # planted line is a changed line


def test_run_order_interleaved():
    first = [p["category"] for p in plant.ORDER[:10]]
    assert len(set(first)) >= 8 and "clean" in first


def test_sample_repo_base_tests_pass():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(plant.REPO)], check=False, capture_output=True, text=True)  # fmt: skip
    assert p.returncode == 0, p.stdout[-500:]


def test_hit_within_two_lines_and_duplicates():
    s = score_pr(TRUTH, result([F("shop/a.py", 12), F("shop/a.py", 9)], [F("shop/a.py", 13)]))
    assert s["detected"] and s["category_ok"]
    assert s["duplicates"] == 1 and s["code_fp"] == 1


def test_wrong_category_counted():
    s = score_pr(TRUTH, result([F("shop/a.py", 10, "security")]))
    assert s["detected"] and not s["category_ok"]


def test_missing_tests_notes_never_false_positives():
    s = score_pr({**TRUTH, "category": "clean", "expected_reviewer": None, "file": None,
                  "line": None}, result(summary=[F("shop/a.py", None, "tests")]))  # fmt: skip
    assert s["code_fp"] == 0 and s["missing_tests_notes"] == 1


def test_missing_test_pr_hit_by_tests_reviewer():
    truth = {**TRUTH, "category": "missing_test", "expected_reviewer": "tests"}
    s = score_pr(truth, result(summary=[F("shop/a.py", None, "tests")]))
    assert s["detected"] and s["category_ok"] and s["missing_tests_notes"] == 0


def test_test_file_echo_and_misplaced_summary():
    s = score_pr(
        TRUTH, result(summary=[F("shop/a.py", 10), F("tests/test_a.py", 4, bumped_by_tests=True)])
    )
    assert s["echoes"] == 1 and s["echoes_bumped"] == 1 and s["code_fp"] == 0
    assert s["misplaced_summary"] == 1 and s["summary_code_findings"] == 2


def test_aggregate_splits_bug_and_clean():
    rows = [score_pr(TRUTH, result([F("shop/a.py", 10)])),
            score_pr({**TRUTH, "category": "clean", "file": None, "line": None},
                     result([F("shop/a.py", 3)]))]  # fmt: skip
    a = aggregate(rows, 2)
    assert a["detection_rate"] == 1.0
    assert a["code_fp_per_pr"] == {"bug_prs": 0.0, "clean_prs": 1.0}


def test_manual_review_unrelated_and_not_duplicate():
    other = F("shop/a.py", 9, "security")
    r = result([F("shop/a.py", 10), other])
    assert score_pr(TRUTH, r)["duplicates"] == 1
    s = score_pr(TRUTH, r, {"unrelated": [other]})
    assert s["detected"] and s["duplicates"] == 0 and s["code_fp"] == 1
    assert score_pr(TRUTH, r, {"not_duplicate": [other]})["duplicates"] == 0
    miss = score_pr(TRUTH, result([other]), {"unrelated": [other]})
    assert not miss["detected"] and miss["code_fp"] == 1
