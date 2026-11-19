from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_webhook_secret: str = ""
    github_app_id: str = ""
    groq_api_key: str = ""
    github_private_key_path: str = (
        ""  # path to the .pem; the file is read only inside github/auth.py
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    checkpoint_db: str = "data/checkpoints.sqlite"


def get_settings() -> Settings:
    return Settings()
