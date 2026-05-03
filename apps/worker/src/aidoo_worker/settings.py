import ipaddress
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, model_validator
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
            "DOOWON_QDRANT_URL",
        ),
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_API_KEY",
            "DOOWON_AIDOO_QDRANT_API_KEY",
            "DOOWON_WORKER_AIDOO_QDRANT_API_KEY",
            "DOOWON_QDRANT_API_KEY",
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
    rag_deepinfra_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_DEEPINFRA_API_KEY",
            "DOOWON_AIDOO_DEEPINFRA_API_KEY",
            "DOOWON_WORKER_AIDOO_DEEPINFRA_API_KEY",
            "DEEPINFRA_API_KEY",
        ),
    )
    rag_deepinfra_base_url: str = Field(
        default="https://api.deepinfra.com/v1/openai",
        validation_alias=AliasChoices(
            "AIDOO_DEEPINFRA_BASE_URL",
            "DOOWON_AIDOO_DEEPINFRA_BASE_URL",
            "DOOWON_WORKER_AIDOO_DEEPINFRA_BASE_URL",
            "DEEPINFRA_BASE_URL",
        ),
    )
    rag_deepinfra_embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-8B",
        validation_alias=AliasChoices(
            "AIDOO_DEEPINFRA_EMBEDDING_MODEL",
            "DOOWON_AIDOO_DEEPINFRA_EMBEDDING_MODEL",
            "DOOWON_WORKER_AIDOO_DEEPINFRA_EMBEDDING_MODEL",
            "DEEPINFRA_EMBEDDING_MODEL",
        ),
    )
    rag_deepinfra_reranker_model: str = Field(
        default="Qwen/Qwen3-Reranker-8B",
        validation_alias=AliasChoices(
            "AIDOO_DEEPINFRA_RERANKER_MODEL",
            "DOOWON_AIDOO_DEEPINFRA_RERANKER_MODEL",
            "DOOWON_WORKER_AIDOO_DEEPINFRA_RERANKER_MODEL",
            "DEEPINFRA_RERANKER_MODEL",
        ),
    )
    rag_deepinfra_timeout: float = Field(
        default=60.0,
        gt=0,
        le=3600,
        validation_alias=AliasChoices(
            "AIDOO_DEEPINFRA_TIMEOUT",
            "DOOWON_AIDOO_DEEPINFRA_TIMEOUT",
            "DOOWON_WORKER_AIDOO_DEEPINFRA_TIMEOUT",
            "DEEPINFRA_TIMEOUT",
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
    opensearch_url: str = Field(
        default="http://127.0.0.1:59200",
        validation_alias=AliasChoices(
            "DOOWON_WORKER_OPENSEARCH_URL",
            "DOOWON_API_OPENSEARCH_URL",
            "DOOWON_OPENSEARCH_URL",
        ),
    )
    opensearch_index_prefix: str = Field(
        default="aidoo",
        validation_alias=AliasChoices(
            "DOOWON_WORKER_OPENSEARCH_INDEX_PREFIX",
            "DOOWON_API_OPENSEARCH_INDEX_PREFIX",
            "DOOWON_OPENSEARCH_INDEX_PREFIX",
        ),
    )
    image_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_ENABLED",
            "DOOWON_WORKER_IMAGE_ENABLED",
        ),
    )
    image_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_API_KEY",
            "DOOWON_WORKER_IMAGE_API_KEY",
        ),
    )
    image_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_BASE_URL",
            "DOOWON_WORKER_IMAGE_BASE_URL",
        ),
    )
    image_model: str = Field(
        default="gpt-image-2",
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_MODEL",
            "DOOWON_WORKER_IMAGE_MODEL",
        ),
    )
    image_supervisor_model: str = Field(
        default="gpt-5.5",
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_SUPERVISOR_MODEL",
            "DOOWON_WORKER_IMAGE_SUPERVISOR_MODEL",
        ),
    )
    image_agent_web_search_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_AGENT_WEB_SEARCH_ENABLED",
            "DOOWON_WORKER_IMAGE_AGENT_WEB_SEARCH_ENABLED",
        ),
    )
    image_agent_max_iterations: int = Field(
        default=10,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_AGENT_MAX_ITER",
            "DOOWON_WORKER_IMAGE_AGENT_MAX_ITER",
        ),
    )
    image_max_reference_uploads: int = Field(
        default=4,
        ge=1,
        le=12,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_MAX_REFS",
            "DOOWON_WORKER_IMAGE_MAX_REFS",
        ),
    )
    image_reference_max_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=64 * 1024,
        le=64 * 1024 * 1024,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_REFERENCE_MAX_BYTES",
            "DOOWON_WORKER_IMAGE_REFERENCE_MAX_BYTES",
        ),
    )
    image_request_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias=AliasChoices(
            "DOOWON_IMAGE_REQUEST_TIMEOUT_SECONDS",
            "DOOWON_WORKER_IMAGE_REQUEST_TIMEOUT_SECONDS",
        ),
    )

    llm_external_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "DOOWON_LLM_EXTERNAL_API_KEY",
            "DOOWON_WORKER_LLM_EXTERNAL_API_KEY",
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

    @model_validator(mode="after")
    def _validate_rag_runtime_config(self) -> "Settings":
        uses_deepinfra = self.rag_enabled and (
            self.rag_embedding_provider == "deepinfra"
            or self.rag_rerank_provider == "deepinfra"
        )
        if not uses_deepinfra:
            return self

        self.rag_deepinfra_base_url = _normalize_rag_deepinfra_base_url(
            self.rag_deepinfra_base_url
        )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _normalize_rag_deepinfra_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https":
        raise ValueError("RAG DeepInfra base URL must use HTTPS.")
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("RAG DeepInfra base URL must include a hostname.")
    if hostname.lower() == "localhost":
        raise ValueError("RAG DeepInfra base URL must not target localhost.")
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return normalized
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise ValueError("RAG DeepInfra base URL must not target a private-network host.")
    return normalized
