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
    # Accepts OPENAI_API_KEY (conventional) or APP_OPENAI_API_KEY (prefixed).
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "APP_OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("OPENAI_MODEL", "APP_OPENAI_MODEL"),
    )

    model_config = {"env_prefix": "APP_"}


settings = Settings()
