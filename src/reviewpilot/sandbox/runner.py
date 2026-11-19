"""Run a PR's tests in a locked-down Docker container. PR code never runs on the host."""

import io
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

IMAGE = "reviewpilot-sandbox:latest"
TIMEOUT = 120  # seconds
MAX_TARBALL = 50 * 2**20
MAX_UNPACKED = 200 * 2**20
MAX_FAILED = 10

_SUMMARY = re.compile(r"^(?:FAILED|ERROR) (.+)$", re.MULTILINE)
_PASSED = re.compile(r"(\d+) passed")


@dataclass
class SandboxResult:
    passed: int = 0
    failed: list[str] = field(default_factory=list)  # "test_x.py::test_y - Error: msg" (untrusted)
    timed_out: bool = False
    error: str | None = None  # set when there is no test signal


def docker_cmd(src: Path, name: str, timeout: int = TIMEOUT, image: str = IMAGE) -> list[str]:
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", "none",
        "--user", "10001:10001",
        "--read-only",
        "--mount", f"type=bind,src={src},dst=/src,readonly",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--memory", "512m", "--memory-swap", "512m", "--cpus", "1", "--pids-limit", "128",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--workdir", "/src",
        image,
        # inner timeout too: the container ends itself even if the host-side kill misses
        "timeout", "-s", "KILL", str(timeout),
        "python", "-m", "pytest", "-q", "-rfE", "--tb=line", "--color=no", "-p", "no:cacheprovider",
    ]  # fmt: skip


def parse_pytest(out: str, code: int, err: str = "") -> SandboxResult:
    if code == 5:
        return SandboxResult(error="no tests found")
    failed = _SUMMARY.findall(out)
    if code not in (0, 1) and not failed:
        reason = "killed (memory or time limit)" if code == 137 else (err or out).strip()[-300:]
        return SandboxResult(error=f"exit {code}: {reason}")
    lines = [line for line in out.strip().splitlines() if line.strip()]
    m = _PASSED.search(lines[-1]) if lines else None
    shown = [f[:200] for f in failed[:MAX_FAILED]]
    if len(failed) > MAX_FAILED:
        shown.append(f"... and {len(failed) - MAX_FAILED} more")
    return SandboxResult(passed=int(m.group(1)) if m else 0, failed=shown)


def run_tests(src: Path, timeout: int = TIMEOUT, image: str = IMAGE) -> SandboxResult:
    name = f"rp-sandbox-{uuid.uuid4().hex[:12]}"
    try:
        p = subprocess.run(
            docker_cmd(src, name, timeout, image),
            check=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout + 15,  # docker start-up overhead on top of the inner limit
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], check=False, capture_output=True)
        return SandboxResult(timed_out=True, error=f"tests exceeded {timeout}s")
    except FileNotFoundError:
        return SandboxResult(error="docker not found")
    if p.returncode in (124, 137) and not _SUMMARY.search(p.stdout):  # inner timeout or OOM
        return SandboxResult(
            timed_out=True, error=f"tests killed after {timeout}s or out of memory"
        )
    return parse_pytest(p.stdout, p.returncode, p.stderr)


def extract(data: bytes, dest: Path) -> Path:
    """Unpack a repo tarball as plain files only; returns the source root."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        if sum(m.size for m in members) > MAX_UNPACKED:
            raise ValueError("repo too large to unpack")
        plain = [m for m in members if m.isfile() or m.isdir()]  # no links or devices
        tar.extractall(dest, members=plain, filter="data")  # rejects ../ and absolute paths
    roots = list(dest.iterdir())
    return roots[0] if len(roots) == 1 and roots[0].is_dir() else dest


def fetch_source(gh, full_name: str, sha: str, dest: Path) -> Path:
    url = gh.get_repo(full_name).get_archive_link("tarball", sha)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read(MAX_TARBALL + 1)
    if len(data) > MAX_TARBALL:
        raise ValueError("repo tarball too large")
    return extract(data, dest)


def sandbox_pr(gh, full_name: str, sha: str, timeout: int = TIMEOUT) -> SandboxResult:
    try:
        with tempfile.TemporaryDirectory(prefix="rp-src-") as tmp:
            return run_tests(fetch_source(gh, full_name, sha, Path(tmp)), timeout)
    except Exception as e:  # noqa: BLE001 - no test signal must not sink the review
        return SandboxResult(error=f"sandbox failed: {e}")


def main(argv: list[str]) -> None:
    """Live run: python -m reviewpilot.sandbox.runner owner/repo 2"""
    from reviewpilot.github.auth import installation_client

    full_name, number = argv[0], int(argv[1])
    gh = installation_client(*full_name.split("/"))
    sha = gh.get_repo(full_name).get_pull(number).head.sha
    r = sandbox_pr(gh, full_name, sha)
    print(f"PR #{number} head={sha[:7]} passed={r.passed} failed={len(r.failed)} "
          f"timed_out={r.timed_out} error={r.error}")  # fmt: skip
    for f in r.failed:
        print(f"  FAILED {f}")


if __name__ == "__main__":
    main(sys.argv[1:])
