# Eval summary, heldout set, corrected (commit fc58b37, 10/10 PRs scored)

- Detection rate: 0.875 (8 bug PRs, +/-2 lines)
- Category accuracy (detected bugs, right reviewer): 1.0
- Code false positives per PR: bug PRs 0.25, clean PRs 0.5
- Missing-tests notes per PR (separate): bug PRs 1.0, clean PRs 1.0
- Duplicates: 0 in 0 PRs; test-file echoes: 1 in 1 PRs (1 bumped)
- Code findings in summary: 1 (of which real bugs that should be inline: 0)
- Tokens per PR (10 PRs not fully cached): mean 2873, p95 5051, total 28731
- Latency per PR: mean 7.4s, p95 25.79s
- PRs with reviewer errors: 0

| Category | PRs | Detected | Rate | Right reviewer | Code FP/PR |
|---|---|---|---|---|---|
| off_by_one | 1 | 1 | 1.0 | 1/1 | 0.0 |
| logic | 1 | 1 | 1.0 | 1/1 | 0.0 |
| missing_null | 1 | 1 | 1.0 | 1/1 | 1.0 |
| sql_injection | 1 | 1 | 1.0 | 1/1 | 0.0 |
| hardcoded_secret | 1 | 1 | 1.0 | 1/1 | 0.0 |
| race_condition | 1 | 1 | 1.0 | 1/1 | 0.0 |
| resource_leak | 1 | 0 | 0.0 | 0/0 | 1.0 |
| missing_test | 1 | 1 | 1.0 | 1/1 | 0.0 |

## Raw vs corrected (manual review of h03, h07)

| Metric | Raw | Corrected |
|---|---|---|
| Detection rate | 1.0 | 0.875 |
| Category accuracy | 0.875 | 1.0 |
| Code FP/PR, bug PRs | 0.0 | 0.25 |
| Code FP/PR, clean PRs | 0.5 | 0.5 |
| Duplicates | 1 | 0 |

Result files were produced at commit(s): f4a2aa2
