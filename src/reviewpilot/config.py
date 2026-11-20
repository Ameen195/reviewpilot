from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute, so .env is found when a client (Claude Desktop) starts us from another directory.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    github_webhook_secret: str = ""
    github_app_id: str = ""
    groq_api_key: str = ""
    github_private_key_path: str = (
        ""  # path to the .pem; the file is read only inside github/auth.py
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    checkpoint_db: str = "data/checkpoints.sqlite"
    allowed_repos: str = ""  # MCP server only: comma-separated owner/repo; empty = any with the App

    @property
    def allowed_repo_set(self) -> set[str]:
        return {r.strip().lower() for r in self.allowed_repos.split(",") if r.strip()}


def get_settings() -> Settings:
    return Settings()
