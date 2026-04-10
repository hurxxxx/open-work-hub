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
    allow_dev_admin_login: bool = True
    api_prefix: str = "/api/v1"
    postgres_dsn: str = Field(
        ...,
        validation_alias=AliasChoices("DOOWON_POSTGRES_DSN"),
    )
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 30)
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias=AliasChoices("DOOWON_MINIO_ENDPOINT"),
    )
    minio_access_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("DOOWON_MINIO_ACCESS_KEY"),
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("DOOWON_MINIO_SECRET_KEY"),
    )
    minio_bucket: str = Field(
        default="aidoo-portal",
        validation_alias=AliasChoices("DOOWON_MINIO_BUCKET"),
    )
    llm_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("DOOWON_LLM_PROVIDER"),
    )
    llm_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        validation_alias=AliasChoices("DOOWON_LLM_BASE_URL"),
    )
    llm_api_key: str = Field(
        default="ollama",
        validation_alias=AliasChoices("DOOWON_LLM_API_KEY"),
    )
    llm_default_model: str = Field(
        default="qwen3.5:35b-a3b-q4_K_M",
        validation_alias=AliasChoices("DOOWON_LLM_DEFAULT_MODEL"),
    )
    llm_request_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=300,
        validation_alias=AliasChoices("DOOWON_LLM_REQUEST_TIMEOUT_SECONDS"),
    )
    llm_healthcheck_on_startup: bool = Field(
        default=True,
        validation_alias=AliasChoices("DOOWON_LLM_HEALTHCHECK_ON_STARTUP"),
    )
    llm_required: bool = Field(
        default=True,
        validation_alias=AliasChoices("DOOWON_LLM_REQUIRED"),
    )

    model_config = SettingsConfigDict(
        env_prefix="DOOWON_API_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
