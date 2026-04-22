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
    # LLM — Local pool (Apple Silicon mlx-lm by default)
    llm_local_provider: str = Field(
        default="mlx-lm",
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_PROVIDER"),
    )
    llm_local_base_url: str = Field(
        default="http://127.0.0.1:8080/v1",
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_BASE_URL"),
    )
    llm_local_api_key: str = Field(
        default="mlx",
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_API_KEY"),
    )
    llm_local_default_model: str = Field(
        default="mlx-community/Qwen3.6-35B-A3B-4bit",
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_DEFAULT_MODEL"),
    )
    llm_local_canonical_model: str = Field(
        default="qwen/qwen3.6-35b-a3b",
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_CANONICAL_MODEL"),
    )
    llm_local_long_generation_timeout_seconds: float = Field(
        default=1200.0,
        gt=0,
        le=3600,
        validation_alias=AliasChoices("DOOWON_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS"),
    )

    # LLM — External pool (OpenRouter today; Anthropic/OpenAI extensions later)
    llm_external_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_ENABLED"),
    )
    llm_external_provider: str = Field(
        default="openrouter",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_PROVIDER"),
    )
    llm_external_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_BASE_URL"),
    )
    llm_external_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_API_KEY"),
    )
    llm_external_default_model: str = Field(
        default="qwen/qwen3.5-35b-a3b",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_DEFAULT_MODEL"),
    )
    llm_external_canonical_model: str = Field(
        default="qwen/qwen3.6-35b-a3b",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_CANONICAL_MODEL"),
    )
    llm_external_long_generation_timeout_seconds: float = Field(
        default=900.0,
        gt=0,
        le=3600,
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS"),
    )
    llm_external_http_referer: str = Field(
        default="",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_HTTP_REFERER"),
    )
    llm_external_title: str = Field(
        default="Doowon Aidoo",
        validation_alias=AliasChoices("DOOWON_LLM_EXTERNAL_TITLE"),
    )

    # LLM — shared control-plane settings
    llm_request_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
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
    ai_tool_calling_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "AI_TOOL_CALLING_ENABLED",
            "DOOWON_AI_TOOL_CALLING_ENABLED",
            "DOOWON_API_AI_TOOL_CALLING_ENABLED",
        ),
    )
    ai_mcp_bridge_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AIDOO_AI_MCP_BRIDGE_ENABLED",
            "DOOWON_AIDOO_AI_MCP_BRIDGE_ENABLED",
            "DOOWON_API_AIDOO_AI_MCP_BRIDGE_ENABLED",
        ),
    )
    ai_write_tools_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AIDOO_AI_WRITE_TOOLS_ENABLED",
            "DOOWON_AIDOO_AI_WRITE_TOOLS_ENABLED",
            "DOOWON_API_AIDOO_AI_WRITE_TOOLS_ENABLED",
        ),
    )
    ai_agent_max_turns: int = Field(
        default=8,
        ge=1,
        le=32,
        validation_alias=AliasChoices(
            "AI_AGENT_MAX_TURNS",
            "DOOWON_AI_AGENT_MAX_TURNS",
            "DOOWON_API_AI_AGENT_MAX_TURNS",
        ),
    )
    ai_agent_max_tool_calls: int = Field(
        default=16,
        ge=1,
        le=64,
        validation_alias=AliasChoices(
            "AI_AGENT_MAX_TOOL_CALLS",
            "DOOWON_AI_AGENT_MAX_TOOL_CALLS",
            "DOOWON_API_AI_AGENT_MAX_TOOL_CALLS",
        ),
    )
    ai_agent_max_consecutive_tool_errors: int = Field(
        default=3,
        ge=1,
        le=16,
        validation_alias=AliasChoices(
            "AI_AGENT_MAX_CONSECUTIVE_TOOL_ERRORS",
            "DOOWON_AI_AGENT_MAX_CONSECUTIVE_TOOL_ERRORS",
            "DOOWON_API_AI_AGENT_MAX_CONSECUTIVE_TOOL_ERRORS",
        ),
    )
    rag_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AIDOO_RAG_ENABLED",
            "DOOWON_AIDOO_RAG_ENABLED",
            "DOOWON_API_AIDOO_RAG_ENABLED",
        ),
    )
    rag_ui_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AIDOO_RAG_UI_ENABLED",
            "DOOWON_AIDOO_RAG_UI_ENABLED",
            "DOOWON_API_AIDOO_RAG_UI_ENABLED",
        ),
    )
    rag_query_timeout_ms: int = Field(
        default=2500,
        ge=100,
        le=120000,
        validation_alias=AliasChoices(
            "AIDOO_RAG_QUERY_TIMEOUT_MS",
            "DOOWON_AIDOO_RAG_QUERY_TIMEOUT_MS",
            "DOOWON_API_AIDOO_RAG_QUERY_TIMEOUT_MS",
        ),
    )
    rag_grounded_answer_timeout_ms: int = Field(
        default=7000,
        ge=100,
        le=300000,
        validation_alias=AliasChoices(
            "AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
            "DOOWON_AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
            "DOOWON_API_AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS",
        ),
    )
    rag_qdrant_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_URL",
            "DOOWON_AIDOO_QDRANT_URL",
            "DOOWON_API_AIDOO_QDRANT_URL",
        ),
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_API_KEY",
            "DOOWON_AIDOO_QDRANT_API_KEY",
            "DOOWON_API_AIDOO_QDRANT_API_KEY",
        ),
    )
    rag_qdrant_collection_prefix: str = Field(
        default="doowon-rag",
        validation_alias=AliasChoices(
            "AIDOO_QDRANT_COLLECTION_PREFIX",
            "DOOWON_AIDOO_QDRANT_COLLECTION_PREFIX",
            "DOOWON_API_AIDOO_QDRANT_COLLECTION_PREFIX",
        ),
    )
    rag_vector_index_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_VECTOR_INDEX_PROVIDER",
            "DOOWON_AIDOO_VECTOR_INDEX_PROVIDER",
            "DOOWON_API_AIDOO_VECTOR_INDEX_PROVIDER",
        ),
    )
    rag_embedding_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_EMBEDDING_PROVIDER",
            "DOOWON_AIDOO_EMBEDDING_PROVIDER",
            "DOOWON_API_AIDOO_EMBEDDING_PROVIDER",
        ),
    )
    rag_ocr_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_OCR_PROVIDER",
            "DOOWON_AIDOO_OCR_PROVIDER",
            "DOOWON_API_AIDOO_OCR_PROVIDER",
        ),
    )
    rag_rerank_provider: str = Field(
        default="fake",
        validation_alias=AliasChoices(
            "AIDOO_RERANK_PROVIDER",
            "DOOWON_AIDOO_RERANK_PROVIDER",
            "DOOWON_API_AIDOO_RERANK_PROVIDER",
        ),
    )
    otel_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_ENABLED",
            "DOOWON_API_OTEL_ENABLED",
        ),
    )
    otel_console_exporter: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_CONSOLE_EXPORTER",
            "DOOWON_API_OTEL_CONSOLE_EXPORTER",
        ),
    )
    otel_otlp_exporter_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_OTLP_EXPORTER_ENABLED",
            "DOOWON_API_OTEL_OTLP_EXPORTER_ENABLED",
        ),
    )
    otel_metrics_export_interval_ms: int = Field(
        default=60000,
        ge=1000,
        le=300000,
        validation_alias=AliasChoices(
            "DOOWON_OTEL_METRICS_EXPORT_INTERVAL_MS",
            "DOOWON_API_OTEL_METRICS_EXPORT_INTERVAL_MS",
        ),
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
