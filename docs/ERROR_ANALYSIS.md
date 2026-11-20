# Error analysis - Phase 6 evaluation (baseline)

Source: `eval/results/summary.json` / `summary.md` and `eval/results/prs/*.json`; 50/50 PRs
(40 planted bugs in 8 categories + 10 clean), run 2026-11-19 on Groq free tier (gpt-oss-120b for
bug/security, gpt-oss-20b for tests). Ground truth: `eval/plant.py`. Definitions: top of
`eval/score.py`. Human verdicts for ambiguous matches: `eval/results/manual_review.json`.
This is the baseline before any fixes; the issues below are measured, not fixed.

## Headline numbers (corrected by manual review)

| Metric | Corrected | Raw (line matching only) |
|---|---|---|
| Detection rate (right file, +/-2 lines) | **0.925** (37/40) | 0.975 (39/40) |
| Category accuracy (detected bugs, right reviewer) | **1.0** (37/37) | 0.949 (37/39) |
| Code false positives per PR, bug PRs | **0.1** (4 in 40) | 0.03 (1 in 40) |
| Code false positives per PR, clean PRs | **0.1** (1 in 10) | 0.1 |
| Missing-tests notes per PR (counted separately) | bug PRs 0.9, clean PRs 1.1 | same |
| Duplicates | **1** in 1 PR | 2 |
| Test-file echoes | 4 in 4 PRs (all severity-bumped) | same |
| Tokens per PR (48 PRs; mn1, sq1 were fully cached and are excluded) | mean 2527, p95 4982, total 121312 | |
| Latency per PR (incl. Docker tests, same 48 PRs) | mean 8.0s, p95 16.28s | |
| PRs with reviewer errors | 0 | |

| Category | Detected | Code FP/PR |
|---|---|---|
| off_by_one, missing_null, sql_injection, hardcoded_secret, logic | 5/5 each | 0.0 |
| race_condition | 4/5 | 0.0 |
| resource_leak | 3/5 | 0.6 |
| missing_test | 5/5 | 0.2 |

Manual verdicts (why raw and corrected differ):
- **rl3, rl5 - miss.** The only code finding at the leak line is a security "path traversal:
  path not validated" warning, a different issue. It no longer counts as a hit and counts as a
  code false positive instead.
- **rl4 - false positive.** The same path-traversal warning, one line from the real leak finding.
  Raw scoring called it a duplicate.
- **hs4 - two real secrets, not a duplicate.** In the first run lines 4 and 5 (AWS key id and
  secret) were reported separately. After the re-run with new fake values (below) hs4 reports
  both in one finding, so this verdict currently changes nothing.

## Known issue 1 - test-file echoes (duplicate on the failing test file)

**4 of 4** PRs that add a failing test (ob5, mn2, lg4, lg5) get a second finding on the test file
itself, restating the source bug. All 4 are severity-bumped and land in the summary (no line).
lg4 posts a **critical** summary finding on `tests/test_orders.py` next to the real critical inline
finding on `shop/orders.py:13`, so one bug also creates two items in the human-approval step.

Cause: the bug reviewer reviews the test file too and blames the failing test, and
`failing_test_touches()` matches a test file against its own name (`test_orders.py` is in the
names set built for `tests/test_orders.py`), so the echo is bumped like the real finding.

## Known issue 2 - wrong summary findings

All **4** code findings in the summary are the test-file echoes above. No real bug was pushed into
the summary instead of an inline comment (misplaced hits: 0). In this run the "wrong summary
finding" problem and issue 1 are the same thing.

## Known issue 3 - duplicates

1 true duplicate after review: **sq4**, where security (line 34, high) and bug (line 33, medium)
both report the same `ORDER BY {column}` injection. `merge()` only dedupes the exact same line.
Plus the 4 test-file echoes (issue 1).

## Known issue 4 - "missing tests" notes (counted apart from false positives)

1.1 notes per clean PR and 0.9 per bug PR. Patterns:

- **Notes on PRs that do add tests** (c4, c5, c6, c7): e.g. c6 says "No tests cover the new
  TTLCache.clear method" while the PR adds `test_clear`. Cause: review is per file; when reviewing
  `shop/cache.py` the tests reviewer only sees the test file's *name*, not its content.
- **Low-value notes**: c2 "no tests cover the type annotations"; c9 "no tests for fsum".
- **Tests reviewer reporting bugs**, against its prompt: mn2, lg5, ob5 and rl3 notes describe the
  bug itself. In rl3 this is the *only* place the resource leak is mentioned.

## 5. Misses and code false positives

- **Missed: rc5** (check-then-insert in `add_user_unique` with no UNIQUE constraint). Only the
  tests reviewer commented. The bug reviewer's focus list in `prompts.py` never mentions
  concurrency; 4/5 races were still found.
- **Missed: rl3, rl5** (open() without close). See manual verdicts; the security reviewer's
  path-traversal warning took the line instead.
- **False positives (5):** path traversal on rl3, rl4, rl5 (opening a caller-given path is the
  helper's job); mt4 "ensure_dir does not validate empty string or None"; c8 CSV formula injection
  via the new `header` parameter (debatable: header is caller-supplied, not user data).

## After fixes (fc58b37)

Re-run on 2026-11-20 with fresh caches (every LLM call real), same scorer and same manual-review rules.
Held-out "before" was run at `f4a2aa2` (pre-fix code, via a worktree); original "before" is the baseline
above. Results: `eval/results/after/` (both sets) and `eval/results/heldout_before/`.

**Original set (50 PRs: 40 bug, 10 clean)**

| Metric | Before | After |
|---|---|---|
| Detection rate | 0.925 | 0.975 |
| Category accuracy | 1.0 | 1.0 |
| Code FP/PR, bug PRs | 0.10 | 0.12 |
| Code FP/PR, clean PRs | 0.10 | 0.0 |
| Missing-tests notes/PR, bug / clean | 0.9 / 1.1 | 0.68 / 0.5 |
| Duplicates | 1 | 1 |
| Test-file echoes (bumped) | 4 (4) | 0 (0) |
| Code findings in summary | 4 | 0 |
| Tokens/PR mean / p95 | 2527 / 4982 | 2452 / 4240 |
| Latency/PR mean / p95 | 8.0s / 16.3s | 9.6s / 18.9s |

**Held-out set (10 PRs: 8 bug, 2 clean)**

| Metric | Before | After |
|---|---|---|
| Detection rate | 0.875 | 0.875 |
| Category accuracy | 1.0 | 1.0 |
| Code FP/PR, bug PRs | 0.25 | 0.38 |
| Code FP/PR, clean PRs | 0.5 | 0.5 |
| Missing-tests notes/PR, bug / clean | 1.0 / 1.0 | 0.88 / 0.5 |
| Duplicates | 0 | 0 |
| Test-file echoes (bumped) | 1 (1) | 0 (0) |
| Code findings in summary | 1 | 0 |
| Tokens/PR mean / p95 | 2873 / 5051 | 2729 / 4180 |
| Latency/PR mean / p95 | 7.4s / 25.8s | 9.8s / 18.1s |

**Improved:** test-file echoes 4 -> 0 on the original set (1 -> 0 held-out), and no code findings
land in the summary any more (4 -> 0, 1 -> 0). Original-set race_condition went 4/5 -> 5/5 and the
tests reviewer's notes dropped.

**Unchanged:** held-out detection is 7/8 before and after (the miss is h07, a resource leak). The
held-out race PR (h06) was already caught before the fix, so that fix is not measurable there.
Held-out sample is tiny (code FP 2 vs 3 findings), so treat those differences as noise. Latency is
~2s higher in the after runs, cause not investigated.

**Main open issue:** the bug reviewer reports path traversal on resource-leak code instead of the
leak itself (rl4 and rl5 after the fix; h07 before and after). rl5 and h07 are misses (the only code
finding on the leak line is the path-traversal warning), rl4 gets the real leak finding plus the
path-traversal false positive. Other false positives after the fix: rc4 ("threading is not
imported", false because the import is outside the patch hunk) and h03 (authorization note next to
the real null-deref hit).

## Limits of this evaluation

- 50 small single-purpose PRs on one toy repo written for this eval; real PRs are larger and noisier.
- Logic and off-by-one PRs state the intended behaviour in a docstring (otherwise undetectable).
- Planted secrets are obviously fake (`shoplive-0000-1111-2222-3333`), not real provider formats.
- Category accuracy is per reviewer (bug/security/tests), not per bug type.
- One run at temperature 0; replies are cached, so a re-run reproduces these numbers.
- Provenance: 45 results were produced at `1fb4d58`, the unpushed first version of commit
  `ae20042`. The amend only replaced the fake secret values in `eval/plant.py` (hs1-hs5, re-run at
  `ae20042`) and added the manual review to the scorer; the review code is identical.
  Result files say `dirty: true` only because `eval/results/` was untracked during the run.
