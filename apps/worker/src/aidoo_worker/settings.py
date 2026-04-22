from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[4]


WORKSPACE_ROOT = _workspace_root()
ENV_FILE = WORKSPACE_ROOT / ".env"


class Settings(BaseSettings):
    broker_url: str = "redis://127.0.0.1:6379/0"
    result_backend: str = "redis://127.0.0.1:6379/1"
    postgres_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("DOOWON_WORKER_POSTGRES_DSN", "DOOWON_POSTGRES_DSN"),
    )
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias=AliasChoices("DOOWON_WORKER_MINIO_ENDPOINT", "DOOWON_MINIO_ENDPOINT"),
    )
    minio_access_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("DOOWON_WORKER_MINIO_ACCESS_KEY", "DOOWON_MINIO_ACCESS_KEY"),
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        validation_alias=AliasChoices("DOOWON_WORKER_MINIO_SECRET_KEY", "DOOWON_MINIO_SECRET_KEY"),
    )
    minio_bucket: str = Field(
        default="aidoo-portal",
        validation_alias=AliasChoices("DOOWON_WORKER_MINIO_BUCKET", "DOOWON_MINIO_BUCKET"),
    )
    rag_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AIDOO_RAG_ENABLED",
            "DOOWON_AIDOO_RAG_ENABLED",
            "DOOWON_WORKER_AIDOO_RAG_ENABLED",
        ),
    )
    rag_query_timeout_ms: int = Field(
        default=2500,
        ge=100,
        le=120000,
        validation_alias=AliasChoices(
            "AIDOO_RAG_QUERY_TIMEOUT_MS",
            "DOOWON_AIDOO_RAG_QUERY_TIMEOUT_MS",
            "DOOWON_WORKER_AIDOO_RAG_QUERY_TIMEOUT_MS",
        ),
    )
    rag_grounded_answer_timeout_ms: int = Field(
        default=7000,
        ge=100,
        le=300000,
        validation_alias=AliasChoices(
            "AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
            "DOOWON_AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
            "DOOWON_WORKER_AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
        ),
    )
    rag_qdrant_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_URL",
            "DOOWON_AIDOO_QDRANT_URL",
            "DOOWON_WORKER_AIDOO_QDRANT_URL",
        ),
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_API_KEY",
            "DOOWON_AIDOO_QDRANT_API_KEY",
            "DOOWON_WORKER_AIDOO_QDRANT_API_KEY",
        ),
    )
    rag_qdrant_collection_prefix: str = Field(
        default="doowon-rag",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_COLLECTION_PREFIX",
            "DOOWON_AIDOO_QDRANT_COLLECTION_PREFIX",
            "DOOWON_WORKER_AIDOO_QDRANT_COLLECTION_PREFIX",
        ),
    )
    rag_vector_index_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_VECTOR_INDEX_PROVIDER",
            "DOOWON_AIDOO_VECTOR_INDEX_PROVIDER",
            "DOOWON_WORKER_AIDOO_VECTOR_INDEX_PROVIDER",
        ),
    )
    rag_embedding_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_EMBEDDING_PROVIDER",
            "DOOWON_AIDOO_EMBEDDING_PROVIDER",
            "DOOWON_WORKER_AIDOO_EMBEDDING_PROVIDER",
        ),
    )
    rag_ocr_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_OCR_PROVIDER",
            "DOOWON_AIDOO_OCR_PROVIDER",
            "DOOWON_WORKER_AIDOO_OCR_PROVIDER",
        ),
    )
    rag_rerank_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_RERANK_PROVIDER",
            "DOOWON_AIDOO_RERANK_PROVIDER",
            "DOOWON_WORKER_AIDOO_RERANK_PROVIDER",
        ),
    )
    rag_backfill_batch_size: int = Field(
        default=25,
        ge=1,
        le=500,
        validation_alias=AliasChoices(
            "AIDOO_RAG_BACKFILL_BATCH_SIZE",
            "DOOWON_AIDOO_RAG_BACKFILL_BATCH_SIZE",
            "DOOWON_WORKER_AIDOO_RAG_BACKFILL_BATCH_SIZE",
        ),
    )
    rag_backfill_throttle_ms: int = Field(
        default=50,
        ge=0,
        le=60000,
        validation_alias=AliasChoices(
            "AIDOO_RAG_BACKFILL_THROTTLE_MS",
            "DOOWON_AIDOO_RAG_BACKFILL_THROTTLE_MS",
            "DOOWON_WORKER_AIDOO_RAG_BACKFILL_THROTTLE_MS",
        ),
    )
    rag_job_max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "AIDOO_RAG_JOB_MAX_ATTEMPTS",
            "DOOWON_AIDOO_RAG_JOB_MAX_ATTEMPTS",
            "DOOWON_WORKER_AIDOO_RAG_JOB_MAX_ATTEMPTS",
        ),
    )
    rag_job_retry_backoff_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        validation_alias=AliasChoices(
            "AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS",
            "DOOWON_AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS",
            "DOOWON_WORKER_AIDOO_RAG_JOB_RETRY_BACKOFF_SECONDS",
        ),
    )
    rag_job_processing_lease_seconds: int = Field(
        default=2100,
        ge=60,
        le=7200,
        validation_alias=AliasChoices(
            "AIDOO_RAG_JOB_PROCESSING_LEASE_SECONDS",
            "DOOWON_AIDOO_RAG_JOB_PROCESSING_LEASE_SECONDS",
            "DOOWON_WORKER_AIDOO_RAG_JOB_PROCESSING_LEASE_SECONDS",
        ),
    )
    otel_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_ENABLED",
            "DOOWON_WORKER_OTEL_ENABLED",
        ),
    )
    otel_console_exporter: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_CONSOLE_EXPORTER",
            "DOOWON_WORKER_OTEL_CONSOLE_EXPORTER",
        ),
    )
    otel_otlp_exporter_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_OTLP_EXPORTER_ENABLED",
            "DOOWON_WORKER_OTEL_OTLP_EXPORTER_ENABLED",
        ),
    )
    otel_metrics_export_interval_ms: int = Field(
        default=60000,
        ge=1000,
        le=300000,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_METRICS_EXPORT_INTERVAL_MS",
            "DOOWON_WORKER_OTEL_METRICS_EXPORT_INTERVAL_MS",
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="DOOWON_WORKER_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
