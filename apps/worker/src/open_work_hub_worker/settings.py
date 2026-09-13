from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
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
        validation_alias="OPEN_WORK_HUB_POSTGRES_DSN",
    )
    queue_group: str = Field(
        default="all",
        validation_alias="OPEN_WORK_HUB_WORKER_QUEUE_GROUP",
    )
    env_profile: str = Field(
        default="local",
        validation_alias="OPEN_WORK_HUB_ENV_PROFILE",
    )
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias="OPEN_WORK_HUB_MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(
        default="minioadmin",
        validation_alias="OPEN_WORK_HUB_MINIO_ACCESS_KEY",
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        validation_alias="OPEN_WORK_HUB_MINIO_SECRET_KEY",
    )
    minio_bucket: str = Field(
        default="open-work-hub-portal",
        validation_alias="OPEN_WORK_HUB_MINIO_BUCKET",
    )
    asr_backend: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_WORK_HUB_API_ASR_BACKEND",
    )
    llm_external_allowed_providers: str = Field(
        default="openai,anthropic,gemini",
        validation_alias="OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS",
    )
    ai_allowed_external_providers: str = Field(
        default="openai,anthropic,gemini,kipris",
        validation_alias="OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS",
    )
    ai_default_external_llm_provider: str = Field(
        default="openai",
        validation_alias="OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER",
    )
    ai_default_external_search_provider: str = Field(
        default="openai",
        validation_alias="OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER",
    )
    ai_external_llm_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_LLM_ENABLED",
    )
    ai_external_planner_execution_adapter: str = Field(
        default="mock",
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_PLANNER_EXECUTION_ADAPTER",
    )
    ai_external_planner_execution_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_PLANNER_EXECUTION_ENABLED",
    )
    ai_external_planning_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_PLANNING_ENABLED",
    )
    ai_external_quality_review_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_QUALITY_REVIEW_ENABLED",
    )
    ai_external_reasoning_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_REASONING_ENABLED",
    )
    ai_external_search_execution_adapter: str = Field(
        default="mock",
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ADAPTER",
    )
    ai_external_search_execution_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ENABLED",
    )
    rag_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_RAG_ENABLED",
    )
    files_retrieval_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_FILES_RETRIEVAL_ENABLED",
    )
    rag_query_timeout_ms: int = Field(
        default=210000,
        ge=100,
        le=600000,
        validation_alias="OPEN_WORK_HUB_RAG_QUERY_TIMEOUT_MS",
    )
    rag_qdrant_url: str = Field(
        default="",
        validation_alias="OPEN_WORK_HUB_RAG_QDRANT_URL",
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias="OPEN_WORK_HUB_RAG_QDRANT_API_KEY",
    )
    rag_qdrant_collection_prefix: str = Field(
        default="open-work-hub-dev-rag",
        validation_alias="OPEN_WORK_HUB_RAG_QDRANT_COLLECTION_PREFIX",
    )
    rag_vector_index_provider: str = Field(
        default="fake",
        validation_alias="OPEN_WORK_HUB_RAG_VECTOR_INDEX_PROVIDER",
    )
    rag_embedding_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_PROVIDER",
    )
    rag_ocr_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_WORK_HUB_RAG_OCR_PROVIDER",
    )
    rag_rerank_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_WORK_HUB_RAG_RERANK_PROVIDER",
    )
    rag_rerank_candidate_k: int = Field(
        default=80,
        ge=1,
        le=100,
        validation_alias="OPEN_WORK_HUB_RAG_RERANK_CANDIDATE_K",
    )
    rag_preload_on_startup: bool = Field(
        default=True,
        validation_alias="OPEN_WORK_HUB_RAG_PRELOAD_ON_STARTUP",
    )
    rag_fail_startup_on_preload_error: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_RAG_FAIL_STARTUP_ON_PRELOAD_ERROR",
    )
    inference_gateway_base_url: str = Field(
        default="http://127.0.0.1:18080",
        validation_alias="OPEN_WORK_HUB_INFERENCE_GATEWAY_BASE_URL",
    )
    inference_gateway_api_key: str = Field(
        default="local",
        validation_alias="OPEN_WORK_HUB_INFERENCE_GATEWAY_API_KEY",
    )
    rag_local_embedding_model: str = Field(
        default="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_MODEL",
    )
    rag_local_embedding_revision: str | None = Field(
        default="55ec6e9358a56d56af759bc8372e970caf8c305f",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_REVISION",
    )
    rag_local_embedding_device: str = Field(
        default="auto",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_DEVICE",
    )
    rag_local_embedding_dtype: str = Field(
        default="bfloat16",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_DTYPE",
    )
    rag_local_embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_BATCH_SIZE",
    )
    rag_local_embedding_max_seq_length: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_MAX_SEQ_LENGTH",
    )
    rag_local_embedding_normalize: bool = Field(
        default=True,
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_NORMALIZE",
    )
    rag_local_embedding_query_prompt_name: str = Field(
        default="query",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_QUERY_PROMPT_NAME",
    )
    rag_local_embedding_query_prefix: str = Field(
        default="",
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_QUERY_PREFIX",
    )
    rag_local_embedding_trust_remote_code: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_RAG_EMBEDDING_TRUST_REMOTE_CODE",
    )
    rag_local_reranker_model: str = Field(
        default="dragonkue/bge-reranker-v2-m3-ko",
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_MODEL",
    )
    rag_local_reranker_revision: str | None = Field(
        default="2aca5884ecac490192af9ebd86836d9073d826cd",
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_REVISION",
    )
    rag_local_reranker_device: str = Field(
        default="auto",
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_DEVICE",
    )
    rag_local_reranker_dtype: str = Field(
        default="bfloat16",
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_DTYPE",
    )
    rag_local_reranker_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_BATCH_SIZE",
    )
    rag_local_reranker_max_length: int = Field(
        default=512,
        ge=128,
        le=8192,
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_MAX_LENGTH",
    )
    rag_local_reranker_trust_remote_code: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_RAG_RERANKER_TRUST_REMOTE_CODE",
    )
    rag_docling_force_ocr: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_RAG_DOCLING_FORCE_OCR",
    )
    rag_docling_ocr_engine: str = Field(
        default="easyocr",
        validation_alias="OPEN_WORK_HUB_RAG_DOCLING_OCR_ENGINE",
    )
    rag_docling_ocr_langs: str = Field(
        default="ko,en",
        validation_alias="OPEN_WORK_HUB_RAG_DOCLING_OCR_LANGS",
    )
    rag_docling_min_text_chars: int = Field(
        default=128,
        ge=0,
        le=10000,
        validation_alias="OPEN_WORK_HUB_RAG_DOCLING_MIN_TEXT_CHARS",
    )
    rag_vision_ocr_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_WORK_HUB_RAG_VISION_OCR_ENABLED",
    )
    rag_vision_ocr_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_WORK_HUB_RAG_VISION_OCR_TIMEOUT_SECONDS",
    )
    rag_vision_ocr_max_pages: int = Field(
        default=2,
        ge=1,
        le=20,
        validation_alias="OPEN_WORK_HUB_RAG_VISION_OCR_MAX_PAGES",
    )
    rag_vision_ocr_dpi: int = Field(
        default=160,
        ge=72,
        le=300,
        validation_alias="OPEN_WORK_HUB_RAG_VISION_OCR_DPI",
    )
    rag_vision_ocr_max_new_tokens: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="OPEN_WORK_HUB_RAG_VISION_OCR_MAX_NEW_TOKENS",
    )
    rag_backfill_batch_size: int = Field(
        default=25,
        ge=1,
        le=500,
        validation_alias="OPEN_WORK_HUB_RAG_BACKFILL_BATCH_SIZE",
    )
    rag_backfill_throttle_ms: int = Field(
        default=50,
        ge=0,
        le=60000,
        validation_alias="OPEN_WORK_HUB_RAG_BACKFILL_THROTTLE_MS",
    )
    rag_job_max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias="OPEN_WORK_HUB_RAG_JOB_MAX_ATTEMPTS",
    )
    rag_job_retry_backoff_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        validation_alias="OPEN_WORK_HUB_RAG_JOB_RETRY_BACKOFF_SECONDS",
    )
    rag_job_processing_lease_seconds: int = Field(
        default=2100,
        ge=60,
        le=7200,
        validation_alias="OPEN_WORK_HUB_RAG_JOB_PROCESSING_LEASE_SECONDS",
    )
    mail_sync_processing_lease_seconds: int = Field(
        default=900,
        ge=60,
        le=7200,
        validation_alias="OPEN_WORK_HUB_MAIL_SYNC_PROCESSING_LEASE_SECONDS",
    )
    opensearch_url: str = Field(
        default="http://127.0.0.1:59210",
        validation_alias="OPEN_WORK_HUB_OPENSEARCH_URL",
    )
    opensearch_index_prefix: str = Field(
        default="open-work-hub-dev",
        validation_alias="OPEN_WORK_HUB_OPENSEARCH_INDEX_PREFIX",
    )
    keyword_search_backend: str = Field(
        default="opensearch",
        validation_alias="OPEN_WORK_HUB_KEYWORD_SEARCH_BACKEND",
    )
    hermes_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_HERMES_ENABLED",
    )
    hermes_runtime_base_url: str = Field(
        default="http://127.0.0.1:8642",
        validation_alias="OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL",
    )
    hermes_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="OPEN_WORK_HUB_HERMES_API_KEY",
        repr=False,
    )
    hermes_request_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        validation_alias="OPEN_WORK_HUB_HERMES_REQUEST_TIMEOUT_SECONDS",
    )
    hermes_run_timeout_seconds: int = Field(
        default=3600,
        ge=60,
        le=3600,
        validation_alias="OPEN_WORK_HUB_HERMES_RUN_TIMEOUT_SECONDS",
    )
    hermes_max_concurrent_runs: int = Field(
        default=10,
        ge=1,
        le=1000,
        validation_alias="OPEN_WORK_HUB_HERMES_MAX_CONCURRENT_RUNS",
    )
    hermes_dispatch_lease_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias="OPEN_WORK_HUB_HERMES_DISPATCH_LEASE_SECONDS",
    )
    otel_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_WORK_HUB_OTEL_ENABLED",
    )
    otel_console_exporter: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_OTEL_CONSOLE_EXPORTER",
    )
    otel_otlp_exporter_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_WORK_HUB_OTEL_OTLP_EXPORTER_ENABLED",
    )
    otel_metrics_export_interval_ms: int = Field(
        default=60000,
        ge=1000,
        le=300000,
        validation_alias="OPEN_WORK_HUB_OTEL_METRICS_EXPORT_INTERVAL_MS",
    )

    model_config = SettingsConfigDict(
        env_prefix="OPEN_WORK_HUB_WORKER_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_hermes_runtime(self) -> "Settings":
        self.hermes_runtime_base_url = self.hermes_runtime_base_url.strip().rstrip("/")
        if not self.hermes_enabled:
            return self
        if not self.hermes_runtime_base_url:
            raise ValueError(
                "OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL is required when Hermes is enabled."
            )
        if len(self.hermes_api_key.get_secret_value()) < 16:
            raise ValueError(
                "OPEN_WORK_HUB_HERMES_API_KEY must be at least 16 characters when Hermes is enabled."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
