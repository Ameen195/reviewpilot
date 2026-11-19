from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    github_webhook_secret: str = ""
    github_app_id: str = ""
    github_private_key_path: str = (
        ""  # path to the .pem; the file is read only inside github/auth.py
    )


def get_settings() -> Settings:
    return Settings()
