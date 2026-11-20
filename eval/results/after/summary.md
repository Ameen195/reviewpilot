# Eval summary, original set, corrected (commit fc58b37, 50/50 PRs scored)

- Detection rate: 0.975 (40 bug PRs, +/-2 lines)
- Category accuracy (detected bugs, right reviewer): 1.0
- Code false positives per PR: bug PRs 0.12, clean PRs 0.0
- Missing-tests notes per PR (separate): bug PRs 0.68, clean PRs 0.5
- Duplicates: 1 in 1 PRs; test-file echoes: 0 in 0 PRs (0 bumped)
- Code findings in summary: 0 (of which real bugs that should be inline: 0)
- Tokens per PR (50 PRs not fully cached): mean 2452, p95 4240, total 122576
- Latency per PR: mean 9.6s, p95 18.91s
- PRs with reviewer errors: 0

| Category | PRs | Detected | Rate | Right reviewer | Code FP/PR |
|---|---|---|---|---|---|
| off_by_one | 5 | 5 | 1.0 | 5/5 | 0.0 |
| missing_null | 5 | 5 | 1.0 | 5/5 | 0.0 |
| sql_injection | 5 | 5 | 1.0 | 5/5 | 0.0 |
| hardcoded_secret | 5 | 5 | 1.0 | 5/5 | 0.0 |
| race_condition | 5 | 5 | 1.0 | 5/5 | 0.2 |
| logic | 5 | 5 | 1.0 | 5/5 | 0.0 |
| resource_leak | 5 | 4 | 0.8 | 4/4 | 0.4 |
| missing_test | 5 | 5 | 1.0 | 5/5 | 0.4 |

## Raw vs corrected (manual review of rc4, rl4, rl5)

| Metric | Raw | Corrected |
|---|---|---|
| Detection rate | 1.0 | 0.975 |
| Category accuracy | 0.975 | 1.0 |
| Code FP/PR, bug PRs | 0.07 | 0.12 |
| Code FP/PR, clean PRs | 0.0 | 0.0 |
| Duplicates | 2 | 1 |

Result files were produced at commit(s): fc58b37
