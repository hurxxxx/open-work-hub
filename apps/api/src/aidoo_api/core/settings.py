from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[5]


WORKSPACE_ROOT = _workspace_root()
ENV_FILE = WORKSPACE_ROOT / ".env"


class Settings(BaseSettings):
    app_name: str = "아이두 API"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    postgres_dsn: str = Field(
        default="sqlite+pysqlite:///./aidoo.db",
        validation_alias=AliasChoices("DOOWON_POSTGRES_DSN"),
    )
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 30)

    model_config = SettingsConfigDict(
        env_prefix="DOOWON_API_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
