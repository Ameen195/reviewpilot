from pathlib import Path

from github import Auth, Github, GithubIntegration

from reviewpilot.config import get_settings


def installation_client(owner: str, repo: str) -> Github:
    """PyGithub client authenticated as the App installation on owner/repo."""
    s = get_settings()
    if not (s.github_app_id and s.github_private_key_path):
        raise RuntimeError("Set GITHUB_APP_ID and GITHUB_PRIVATE_KEY_PATH in .env")
    app_auth = Auth.AppAuth(s.github_app_id, Path(s.github_private_key_path).read_text())
    gi = GithubIntegration(auth=app_auth)
    return gi.get_github_for_installation(gi.get_repo_installation(owner, repo).id)
