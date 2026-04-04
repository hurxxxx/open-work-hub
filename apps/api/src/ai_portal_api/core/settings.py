from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Doowon AI Portal API"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_prefix="DOOWON_API_",
        env_file=".env",
        env_file_encoding="utf-8",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
