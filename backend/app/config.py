from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the repository-root .env from this file's location, not from CWD:
#   backend/app/config.py  →  .parent → backend/app/
#                          →  .parent → backend/
#                          →  .parent → travel-planning-agent/  (repo root)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    app_name: str = "travel-planning-agent"
    debug: bool = False
    # Accepts GOOGLE_API_KEY (conventional) or APP_GOOGLE_API_KEY (prefixed).
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "APP_GOOGLE_API_KEY"),
    )
    # Accepts OPENAI_API_KEY (conventional) or APP_OPENAI_API_KEY (prefixed).
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "APP_OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("OPENAI_MODEL", "APP_OPENAI_MODEL"),
    )
    # Accepts DATABASE_URL (conventional) or APP_DATABASE_URL (prefixed).
    # Defaults to a local SQLite file so the server starts without PostgreSQL.
    database_url: str = Field(
        default="sqlite+aiosqlite:///./travel_planning.db",
        validation_alias=AliasChoices("DATABASE_URL", "APP_DATABASE_URL"),
    )

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )


settings = Settings()
