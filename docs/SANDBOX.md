# Sandbox test runner

ReviewPilot runs a PR's tests so reviewers can use real failures as evidence. PR code never runs
on the host: the head commit is downloaded as a tarball and unpacked as plain files, then pytest
runs inside Docker.

## Locked down

| Rule | How |
|---|---|
| No network | `--network none` |
| Non-root | `--user 10001:10001`, `--cap-drop ALL`, `--security-opt no-new-privileges` |
| Read-only source | bind mount `readonly`, `--read-only` root fs, small `noexec` tmpfs at `/tmp` |
| Limits | `--memory 512m` (no swap), `--cpus 1`, `--pids-limit 128` |
| Time limit | inner `timeout -s KILL` + host-side timeout that runs `docker kill` |
| No secrets | no `-e`/`--env`, no Docker socket, no `/run/secrets`; the image holds only Python + pytest |
| Safe unpack | size caps, regular files/dirs only, `tarfile` `data` filter (blocks `../` and absolute paths) |

Proven by `tests/test_sandbox.py` (Docker tests skip when Docker or the image is missing).

## How results are used

Failing tests are shown to each reviewer inside the untrusted-content tag (test output is
PR-controlled). If a failing test lives in a changed file or in `test_<name>.py` / `<name>_test.py`,
bug and security findings in that file go up one severity level. No tests, a crash or a timeout
means "no test signal" and the review carries on.

## Known limit

The repo's own dependencies are **not installed**: the container never has network. Only tests
that need the standard library and pytest can pass; others show up as import errors.

Future work: install dependencies in a separate, earlier step with
`pip download --only-binary=:all:` (wheels only, so no `setup.py` runs), then mount those wheels
read-only and install them offline inside the sandbox.

## Build the image (once)

```powershell
# in D:\Projects\reviewpilot
docker build -t reviewpilot-sandbox:latest src/reviewpilot/sandbox
```

Run on a PR: `uv run python -m reviewpilot.sandbox.runner owner/repo 2`
