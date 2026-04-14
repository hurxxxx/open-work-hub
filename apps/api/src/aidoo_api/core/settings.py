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
    instance_id: str = Field(
        default="api",
        validation_alias=AliasChoices("DOOWON_API_INSTANCE_ID"),
    )
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
    worker_broker_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices("DOOWON_WORKER_BROKER_URL", "DOOWON_BROKER_URL"),
    )
    worker_result_backend: str = Field(
        default="redis://127.0.0.1:6379/1",
        validation_alias=AliasChoices("DOOWON_WORKER_RESULT_BACKEND", "DOOWON_RESULT_BACKEND"),
    )
    collab_redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias=AliasChoices(
            "DOOWON_API_COLLAB_REDIS_URL",
            "DOOWON_REDIS_URL",
            "DOOWON_WORKER_BROKER_URL",
        ),
    )
    collab_acl_recheck_seconds: int = Field(
        default=15,
        ge=5,
        le=300,
        validation_alias=AliasChoices("DOOWON_API_COLLAB_ACL_RECHECK_SECONDS"),
    )
    collab_snapshot_debounce_ms: int = Field(
        default=2000,
        ge=250,
        le=30000,
        validation_alias=AliasChoices("DOOWON_API_COLLAB_SNAPSHOT_DEBOUNCE_MS"),
    )
    db_pool_size: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias=AliasChoices("DOOWON_API_DB_POOL_SIZE"),
    )
    db_max_overflow: int = Field(
        default=20,
        ge=0,
        le=100,
        validation_alias=AliasChoices("DOOWON_API_DB_MAX_OVERFLOW"),
    )
    db_pool_timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        validation_alias=AliasChoices("DOOWON_API_DB_POOL_TIMEOUT"),
    )
    recording_spool_dir: str = Field(
        default=str(WORKSPACE_ROOT / ".local-recording-spool"),
        validation_alias=AliasChoices("DOOWON_API_RECORDING_SPOOL_DIR"),
    )
    recording_max_size_bytes: int = Field(
        default=1024 * 1024 * 1024,
        ge=1024 * 1024,
        validation_alias=AliasChoices("DOOWON_API_RECORDING_MAX_SIZE_BYTES"),
    )
    recording_staging_retention_hours: int = Field(
        default=24 * 7,
        ge=1,
        le=24 * 30,
        validation_alias=AliasChoices("DOOWON_API_RECORDING_STAGING_RETENTION_HOURS"),
    )
    recording_chunk_seconds: int = Field(
        default=2,
        ge=1,
        le=10,
        validation_alias=AliasChoices("DOOWON_API_RECORDING_CHUNK_SECONDS"),
    )
    asr_backend: str = Field(
        default="cohere",
        validation_alias=AliasChoices("DOOWON_API_ASR_BACKEND", "DOOWON_ASR_BACKEND"),
    )
    asr_cohere_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DOOWON_API_COHERE_API_KEY", "COHERE_API_KEY"),
    )
    asr_cohere_model: str = Field(default="transcribe-v1")
    asr_cohere_base_url: str = Field(default="https://api.cohere.com/v2")
    asr_qwen_model: str = Field(default="Qwen/Qwen3-ASR-1.7B")
    asr_qwen_device: str = Field(default="cuda")
    asr_whisper_model: str = Field(default="large-v3")
    asr_whisper_device: str = Field(default="cuda")
    asr_whisper_compute_type: str = Field(default="float16")
    asr_request_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias=AliasChoices("DOOWON_API_ASR_REQUEST_TIMEOUT_SECONDS"),
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
    llm_canonical_model: str = Field(
        default="qwen/qwen3.5-35b-a3b",
        validation_alias=AliasChoices("DOOWON_LLM_CANONICAL_MODEL", "DOOWON_LLM_MODEL_FAMILY"),
    )
    llm_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("DOOWON_LLM_FALLBACK_ENABLED"),
    )
    llm_fallback_provider: str = Field(
        default="openrouter",
        validation_alias=AliasChoices("DOOWON_LLM_FALLBACK_PROVIDER"),
    )
    llm_fallback_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("DOOWON_LLM_FALLBACK_BASE_URL", "DOOWON_OPENROUTER_BASE_URL"),
    )
    llm_fallback_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DOOWON_LLM_FALLBACK_API_KEY",
            "DOOWON_OPENROUTER_API_KEY",
            "OPENROUTER_API_KEY",
        ),
    )
    llm_fallback_model: str = Field(
        default="qwen/qwen3.5-35b-a3b",
        validation_alias=AliasChoices("DOOWON_LLM_FALLBACK_MODEL"),
    )
    llm_fallback_http_referer: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DOOWON_LLM_FALLBACK_HTTP_REFERER", "DOOWON_OPENROUTER_HTTP_REFERER"
        ),
    )
    llm_fallback_title: str = Field(
        default="Doowon Aidoo",
        validation_alias=AliasChoices("DOOWON_LLM_FALLBACK_TITLE", "DOOWON_OPENROUTER_TITLE"),
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
