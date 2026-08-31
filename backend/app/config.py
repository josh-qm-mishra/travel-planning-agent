from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "travel-planning-agent"
    debug: bool = False

    model_config = {"env_prefix": "APP_"}


settings = Settings()
