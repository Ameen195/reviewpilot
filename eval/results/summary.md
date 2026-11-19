# Eval summary, original set, corrected (commit c4db2c9, 50/50 PRs scored)

- Detection rate: 0.925 (40 bug PRs, +/-2 lines)
- Category accuracy (detected bugs, right reviewer): 1.0
- Code false positives per PR: bug PRs 0.1, clean PRs 0.1
- Missing-tests notes per PR (separate): bug PRs 0.9, clean PRs 1.1
- Duplicates: 1 in 1 PRs; test-file echoes: 4 in 4 PRs (4 bumped)
- Code findings in summary: 4 (of which real bugs that should be inline: 0)
- Tokens per PR (48 PRs not fully cached): mean 2527, p95 4982, total 121312
- Latency per PR: mean 8.0s, p95 16.28s
- PRs with reviewer errors: 0

| Category | PRs | Detected | Rate | Right reviewer | Code FP/PR |
|---|---|---|---|---|---|
| off_by_one | 5 | 5 | 1.0 | 5/5 | 0.0 |
| missing_null | 5 | 5 | 1.0 | 5/5 | 0.0 |
| sql_injection | 5 | 5 | 1.0 | 5/5 | 0.0 |
| hardcoded_secret | 5 | 5 | 1.0 | 5/5 | 0.0 |
| race_condition | 5 | 4 | 0.8 | 4/4 | 0.0 |
| logic | 5 | 5 | 1.0 | 5/5 | 0.0 |
| resource_leak | 5 | 3 | 0.6 | 3/3 | 0.6 |
| missing_test | 5 | 5 | 1.0 | 5/5 | 0.2 |

## Raw vs corrected (manual review of rl3, rl4, rl5, hs4)

| Metric | Raw | Corrected |
|---|---|---|
| Detection rate | 0.975 | 0.925 |
| Category accuracy | 0.949 | 1.0 |
| Code FP/PR, bug PRs | 0.03 | 0.1 |
| Code FP/PR, clean PRs | 0.1 | 0.1 |
| Duplicates | 2 | 1 |

Result files were produced at commit(s): 1fb4d58, ae20042
