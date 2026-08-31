from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "travel-planning-agent"
    debug: bool = False
    # Accepts GOOGLE_API_KEY (conventional) or APP_GOOGLE_API_KEY (prefixed).
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_API_KEY", "APP_GOOGLE_API_KEY"),
    )

    model_config = {"env_prefix": "APP_"}


settings = Settings()
