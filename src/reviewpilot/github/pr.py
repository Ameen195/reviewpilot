from collections.abc import Callable
from itertools import islice

from github import Github, GithubException

from reviewpilot.context.skip import MAX_FILES


def fetch_pr(
    gh: Github, full_name: str, number: int
) -> tuple[dict, list[dict], Callable[[str], str | None]]:
    """Return raw REST dicts (same shape as the test fixtures) and a head-file reader."""
    repo = gh.get_repo(full_name)
    pr = repo.get_pull(number)
    files = [f.raw_data for f in islice(pr.get_files(), MAX_FILES + 1)]
    head_sha = pr.head.sha

    def get_content(path: str) -> str | None:
        try:
            return repo.get_contents(path, ref=head_sha).decoded_content.decode("utf-8", "replace")
        except (GithubException, AssertionError, AttributeError):  # missing, too big, or a dir
            return None

    return pr.raw_data, files, get_content
