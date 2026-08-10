import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import dotenv_values

from open_alm_api.open_alm_desktop_update_manifest import (
    open_alm_desktop_update_dir_values,
)


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[5]


WORKSPACE_ROOT = _workspace_root()
ENV_FILE = WORKSPACE_ROOT / ".env"
DEFAULT_FRONTEND_DIST_DIR = str(WORKSPACE_ROOT / "dist" / "apps" / "web")
DEFAULT_DM_ATTACHMENT_SIGNING_KEY = "dev-dm-attachment-signing-key"
DEFAULT_OPF_CHECKPOINT = "openai/privacy-filter"
PRODUCTION_ENVIRONMENT = "production"
PREVIEW_ENVIRONMENT = "preview"
PRODUCTION_LIKE_ENVIRONMENTS = frozenset({PREVIEW_ENVIRONMENT, PRODUCTION_ENVIRONMENT})


def normalize_runtime_environment(value: str) -> str:
    return (value or "development").strip().lower() or "development"


def is_production_environment(environment: str) -> bool:
    return normalize_runtime_environment(environment) == PRODUCTION_ENVIRONMENT


def is_production_like_environment(environment: str) -> bool:
    return normalize_runtime_environment(environment) in PRODUCTION_LIKE_ENVIRONMENTS


def _settings_env_values() -> dict[str, str | None]:
    values: dict[str, str | None] = dict(dotenv_values(ENV_FILE))
    values.update(os.environ)
    return values


class Settings(BaseSettings):
    app_name: str = "Open ALM API"
    environment: str = "development"
    env_profile: str = Field(
        default="",
        validation_alias="OPEN_ALM_ENV_PROFILE",
    )
    allow_dev_admin_login: bool = True
    dev_login_allowed_hosts: str = ""
    instance_id: str = Field(
        default="api",
        validation_alias="OPEN_ALM_API_INSTANCE_ID",
    )
    api_prefix: str = Field(
        default="/api/v1",
        validation_alias="OPEN_ALM_API_PREFIX",
    )
    open_alm_desktop_update_dirs: dict[str, str] = Field(default_factory=dict)
    postgres_dsn: str = Field(
        ...,
        validation_alias="OPEN_ALM_POSTGRES_DSN",
    )
    session_ttl_hours: int = Field(default=168, ge=1, le=24 * 30)
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias="OPEN_ALM_MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(
        default="minioadmin",
        validation_alias="OPEN_ALM_MINIO_ACCESS_KEY",
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        validation_alias="OPEN_ALM_MINIO_SECRET_KEY",
    )
    minio_bucket: str = Field(
        default="open-alm-portal",
        validation_alias="OPEN_ALM_MINIO_BUCKET",
    )
    drawio_bind_host: str = Field(
        default="127.0.0.1",
        validation_alias="OPEN_ALM_DRAWIO_BIND_HOST",
    )
    drawio_image_tag: str = Field(
        default="30.2.5",
        validation_alias="OPEN_ALM_DRAWIO_IMAGE_TAG",
    )
    drawio_port: int = Field(
        default=18082,
        ge=1,
        le=65535,
        validation_alias="OPEN_ALM_DRAWIO_PORT",
    )
    drawio_server_url: str = Field(
        default="",
        validation_alias="OPEN_ALM_DRAWIO_SERVER_URL",
    )
    dm_attachment_signing_key: str = Field(
        default=DEFAULT_DM_ATTACHMENT_SIGNING_KEY,
        validation_alias="OPEN_ALM_DM_ATTACHMENT_SIGNING_KEY",
    )
    worker_broker_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias="OPEN_ALM_WORKER_BROKER_URL",
    )
    worker_result_backend: str = Field(
        default="redis://127.0.0.1:6379/1",
        validation_alias="OPEN_ALM_WORKER_RESULT_BACKEND",
    )
    mail_credential_encryption_key: str = Field(
        default="",
        validation_alias="OPEN_ALM_MAIL_CREDENTIAL_ENCRYPTION_KEY",
    )
    ai_model_credential_encryption_key: str = Field(
        default="",
        validation_alias="OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
        repr=False,
    )
    mail_allowed_private_hosts: str = Field(
        default="",
        validation_alias="OPEN_ALM_MAIL_ALLOWED_PRIVATE_HOSTS",
    )
    mail_allow_insecure_transport: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_MAIL_ALLOW_INSECURE_TRANSPORT",
    )
    mail_sync_max_messages: int = Field(
        default=50,
        ge=1,
        le=500,
        validation_alias="OPEN_ALM_MAIL_SYNC_MAX_MESSAGES",
    )
    mail_sync_max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias="OPEN_ALM_MAIL_SYNC_MAX_ATTEMPTS",
    )
    mail_sync_retry_backoff_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
        validation_alias="OPEN_ALM_MAIL_SYNC_RETRY_BACKOFF_SECONDS",
    )
    mail_sync_processing_lease_seconds: int = Field(
        default=900,
        ge=60,
        le=7200,
        validation_alias="OPEN_ALM_MAIL_SYNC_PROCESSING_LEASE_SECONDS",
    )
    mail_sync_dispatch_visibility_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias="OPEN_ALM_MAIL_SYNC_DISPATCH_VISIBILITY_SECONDS",
    )
    hr_groupware_auth_url: str = Field(
        default="",
        validation_alias="OPEN_ALM_HR_GROUPWARE_AUTH_URL",
    )
    hr_groupware_auth_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
        validation_alias="OPEN_ALM_HR_GROUPWARE_AUTH_TIMEOUT_SECONDS",
    )
    hr_groupware_sync_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_HR_GROUPWARE_SYNC_ENABLED",
    )
    hr_groupware_sync_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="OPEN_ALM_HR_GROUPWARE_SYNC_HOUR",
    )
    hr_groupware_sync_minute: int = Field(
        default=10,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_HR_GROUPWARE_SYNC_MINUTE",
    )
    hr_groupware_sync_timezone: str = Field(
        default="Asia/Seoul",
        validation_alias="OPEN_ALM_HR_GROUPWARE_SYNC_TIMEZONE",
    )
    erp_hr_snapshot_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_ERP_HR_SNAPSHOT_ENABLED",
    )
    erp_hr_snapshot_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="OPEN_ALM_ERP_HR_SNAPSHOT_HOUR",
    )
    erp_hr_snapshot_minute: int = Field(
        default=20,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_ERP_HR_SNAPSHOT_MINUTE",
    )
    hr_master_sync_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_HR_MASTER_SYNC_ENABLED",
    )
    hr_master_sync_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="OPEN_ALM_HR_MASTER_SYNC_HOUR",
    )
    hr_master_sync_minute: int = Field(
        default=30,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_HR_MASTER_SYNC_MINUTE",
    )
    naver_client_id: str = Field(
        default="",
        validation_alias="OPEN_ALM_NAVER_CLIENT_ID",
    )
    naver_client_secret: str = Field(
        default="",
        validation_alias="OPEN_ALM_NAVER_CLIENT_SECRET",
    )
    news_crawl_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_NEWS_CRAWL_ENABLED",
    )
    # Local-dev only: route news collection onto a private queue so a shared-broker
    # worker on another machine cannot steal the task. Empty = use the contract
    # default ("news"); production leaves this unset.
    news_collect_queue_override: str = Field(
        default="",
        validation_alias="OPEN_ALM_NEWS_COLLECT_QUEUE",
    )
    news_crawl_every_hours: int = Field(
        default=2,
        ge=1,
        le=24,
        validation_alias="OPEN_ALM_NEWS_CRAWL_EVERY_HOURS",
    )
    news_crawl_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_NEWS_CRAWL_MINUTE",
    )
    # When the freshest cached article is older than this, a channel read
    # triggers a background re-collection (best-effort, throttled).
    news_stale_after_hours: int = Field(
        default=12,
        ge=1,
        le=168,
        validation_alias="OPEN_ALM_NEWS_STALE_AFTER_HOURS",
    )
    qna_board_crawl_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_QNA_BOARD_CRAWL_ENABLED",
    )
    qna_board_sync_hour: int = Field(
        default=7,
        ge=0,
        le=23,
        validation_alias="OPEN_ALM_QNA_BOARD_SYNC_HOUR",
    )
    qna_board_sync_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_QNA_BOARD_SYNC_MINUTE",
    )
    # Industry-report aggregator (오토저널 / KDI crawl). Disabled by default like
    # the news crawl; the daily Celery-beat schedule only runs when enabled.
    industry_report_crawl_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_INDUSTRY_REPORT_CRAWL_ENABLED",
    )
    industry_report_crawl_hour: int = Field(
        default=7,
        ge=0,
        le=23,
        validation_alias="OPEN_ALM_INDUSTRY_REPORT_CRAWL_HOUR",
    )
    industry_report_crawl_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="OPEN_ALM_INDUSTRY_REPORT_CRAWL_MINUTE",
    )
    industry_report_upload_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        validation_alias="OPEN_ALM_INDUSTRY_REPORT_UPLOAD_MAX_BYTES",
    )
    industry_report_crawl_max_file_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        validation_alias="OPEN_ALM_INDUSTRY_REPORT_CRAWL_MAX_FILE_BYTES",
    )
    opensearch_url: str = Field(
        default="http://127.0.0.1:59210",
        validation_alias="OPEN_ALM_OPENSEARCH_URL",
    )
    opensearch_index_prefix: str = Field(
        default="open-alm-dev",
        validation_alias="OPEN_ALM_OPENSEARCH_INDEX_PREFIX",
    )
    keyword_search_backend: str = Field(
        default="opensearch",
        validation_alias="OPEN_ALM_KEYWORD_SEARCH_BACKEND",
    )
    collab_redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias="OPEN_ALM_API_COLLAB_REDIS_URL",
    )
    realtime_redis_url: str = Field(
        default="redis://127.0.0.1:6379/0",
        validation_alias="OPEN_ALM_API_REALTIME_REDIS_URL",
    )
    collab_acl_recheck_seconds: int = Field(
        default=15,
        ge=5,
        le=300,
        validation_alias="OPEN_ALM_API_COLLAB_ACL_RECHECK_SECONDS",
    )
    collab_snapshot_debounce_ms: int = Field(
        default=2000,
        ge=250,
        le=30000,
        validation_alias="OPEN_ALM_API_COLLAB_SNAPSHOT_DEBOUNCE_MS",
    )
    collab_max_user_room_connections: int = Field(
        default=2,
        ge=1,
        le=50,
        validation_alias="OPEN_ALM_API_COLLAB_MAX_USER_ROOM_CONNECTIONS",
    )
    collab_max_room_clients: int = Field(
        default=100,
        ge=1,
        le=1000,
        validation_alias="OPEN_ALM_API_COLLAB_MAX_ROOM_CLIENTS",
    )
    collab_cleanup_timeout_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        validation_alias="OPEN_ALM_API_COLLAB_CLEANUP_TIMEOUT_SECONDS",
    )
    db_pool_size: int = Field(
        default=32,
        ge=1,
        le=100,
        validation_alias="OPEN_ALM_API_DB_POOL_SIZE",
    )
    db_max_overflow: int = Field(
        default=64,
        ge=0,
        le=100,
        validation_alias="OPEN_ALM_API_DB_MAX_OVERFLOW",
    )
    db_pool_timeout: int = Field(
        default=45,
        ge=1,
        le=300,
        validation_alias="OPEN_ALM_API_DB_POOL_TIMEOUT",
    )
    recording_spool_dir: str = Field(
        default=str(WORKSPACE_ROOT / ".local-recording-spool"),
        validation_alias="OPEN_ALM_API_RECORDING_SPOOL_DIR",
    )
    serve_frontend: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_API_SERVE_FRONTEND",
    )
    frontend_dist_dir: str = Field(
        default=DEFAULT_FRONTEND_DIST_DIR,
        validation_alias="OPEN_ALM_API_FRONTEND_DIST_DIR",
    )
    recording_max_size_bytes: int = Field(
        default=1024 * 1024 * 1024,
        ge=1024 * 1024,
        validation_alias="OPEN_ALM_API_RECORDING_MAX_SIZE_BYTES",
    )
    recording_staging_retention_hours: int = Field(
        default=24 * 7,
        ge=1,
        le=24 * 30,
        validation_alias="OPEN_ALM_API_RECORDING_STAGING_RETENTION_HOURS",
    )
    video_chat_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_API_VIDEO_CHAT_ENABLED",
    )
    livekit_url: str = Field(
        default="ws://127.0.0.1:7880",
        validation_alias="OPEN_ALM_LIVEKIT_URL",
    )
    livekit_public_url: str = Field(
        default="",
        validation_alias="OPEN_ALM_LIVEKIT_PUBLIC_URL",
    )
    livekit_api_key: str = Field(
        default="devkey",
        validation_alias="OPEN_ALM_LIVEKIT_API_KEY",
    )
    livekit_api_secret: str = Field(
        default="devsecret-devsecret-devsecret-0001",
        validation_alias="OPEN_ALM_LIVEKIT_API_SECRET",
    )
    livekit_egress_api_url: str = Field(
        default="",
        validation_alias="OPEN_ALM_LIVEKIT_EGRESS_API_URL",
    )
    video_chat_room_prefix: str = Field(
        default="open-alm",
        validation_alias="OPEN_ALM_VIDEO_CHAT_ROOM_PREFIX",
    )
    video_chat_token_ttl_seconds: int = Field(
        default=3600,
        ge=60,
        le=86400,
        validation_alias="OPEN_ALM_VIDEO_CHAT_TOKEN_TTL_SECONDS",
    )
    video_chat_recording_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_VIDEO_CHAT_RECORDING_ENABLED",
    )
    video_chat_captions_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_VIDEO_CHAT_CAPTIONS_ENABLED",
    )
    legacy_issue_compressor_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_COMPRESSOR_ENABLED",
    )
    dataviz_sysperf_storage_dir: str = Field(
        default=".local-sysperf",
        validation_alias="OPEN_ALM_DATAVIZ_SYSPERF_STORAGE_DIR",
    )
    asr_backend: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_ALM_API_ASR_BACKEND",
    )
    asr_inference_gateway_model: str = Field(
        default="transcribe-v1",
        validation_alias="OPEN_ALM_API_ASR_INFERENCE_GATEWAY_MODEL",
    )
    asr_cohere_api_key: str = Field(
        default="",
        validation_alias="OPEN_ALM_API_COHERE_API_KEY",
    )
    asr_cohere_model: str = Field(
        default="transcribe-v1",
        validation_alias="OPEN_ALM_API_ASR_COHERE_MODEL",
    )
    asr_cohere_base_url: str = Field(
        default="https://api.cohere.com/v2",
        validation_alias="OPEN_ALM_API_ASR_COHERE_BASE_URL",
    )
    asr_qwen_model: str = Field(default="Qwen/Qwen3-ASR-1.7B")
    asr_qwen_device: str = Field(default="cuda")
    asr_whisper_model: str = Field(default="large-v3")
    asr_whisper_device: str = Field(default="cuda")
    asr_whisper_compute_type: str = Field(default="float16")
    asr_request_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_ALM_API_ASR_REQUEST_TIMEOUT_SECONDS",
    )
    inference_gateway_base_url: str = Field(
        default="http://127.0.0.1:18080",
        validation_alias="OPEN_ALM_INFERENCE_GATEWAY_BASE_URL",
    )
    inference_gateway_api_key: str = Field(
        default="local",
        validation_alias="OPEN_ALM_INFERENCE_GATEWAY_API_KEY",
    )
    model_status_request_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
        validation_alias="OPEN_ALM_MODEL_STATUS_REQUEST_TIMEOUT_SECONDS",
    )
    model_status_diagnostic_targets_json: str = Field(
        default="[]",
        validation_alias="OPEN_ALM_MODEL_STATUS_DIAGNOSTIC_TARGETS_JSON",
    )
    # LLM — Local pool (Apple Silicon mlx-lm by default)
    llm_local_provider: str = Field(
        default="mlx-lm",
        validation_alias="OPEN_ALM_LLM_LOCAL_PROVIDER",
    )
    llm_local_base_url: str = Field(
        default="http://127.0.0.1:8080/v1",
        validation_alias="OPEN_ALM_LLM_LOCAL_BASE_URL",
    )
    llm_local_api_key: str = Field(
        default="mlx",
        validation_alias="OPEN_ALM_LLM_LOCAL_API_KEY",
    )
    llm_local_long_generation_timeout_seconds: float = Field(
        default=1200.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_ALM_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS",
    )

    # LLM — External pool (official provider APIs)
    llm_external_allowed_providers: str = Field(
        default="openai,anthropic,gemini",
        validation_alias="OPEN_ALM_LLM_EXTERNAL_ALLOWED_PROVIDERS",
    )
    llm_external_long_generation_timeout_seconds: float = Field(
        default=900.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_ALM_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS",
    )
    # LLM — shared control-plane settings
    llm_request_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_ALM_LLM_REQUEST_TIMEOUT_SECONDS",
    )
    llm_healthcheck_on_startup: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP",
    )
    llm_required: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LLM_REQUIRED",
    )
    opf_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_OPF_ENABLED",
    )
    opf_checkpoint: str = Field(
        default=DEFAULT_OPF_CHECKPOINT,
        validation_alias="OPEN_ALM_OPF_CHECKPOINT",
    )
    opf_cache_dir: str = Field(
        default="",
        validation_alias="OPEN_ALM_OPF_CACHE_DIR",
    )
    opf_device: str = Field(
        default="cpu",
        validation_alias="OPEN_ALM_OPF_DEVICE",
    )
    opf_timeout_ms: int = Field(
        default=10000,
        ge=100,
        le=60000,
        validation_alias="OPEN_ALM_OPF_TIMEOUT_MS",
    )
    opf_max_input_chars: int = Field(
        default=50000,
        ge=100,
        le=500000,
        validation_alias="OPEN_ALM_OPF_MAX_INPUT_CHARS",
    )
    opf_max_concurrency: int = Field(
        default=1,
        ge=1,
        le=8,
        validation_alias="OPEN_ALM_OPF_MAX_CONCURRENCY",
    )
    opf_download_on_startup: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_OPF_DOWNLOAD_ON_STARTUP",
    )
    opf_healthcheck_on_startup: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_OPF_HEALTHCHECK_ON_STARTUP",
    )
    opf_required: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_OPF_REQUIRED",
    )
    opf_service_base_url: str = Field(
        default="http://127.0.0.1:18081",
        validation_alias="OPEN_ALM_OPF_SERVICE_BASE_URL",
    )
    opf_service_timeout_ms: int = Field(
        default=10000,
        ge=100,
        le=60000,
        validation_alias="OPEN_ALM_OPF_SERVICE_TIMEOUT_MS",
    )
    ai_tool_calling_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_AI_TOOL_CALLING_ENABLED",
    )
    ai_conversation_run_lock_ttl_seconds: int = Field(
        default=1800,
        ge=60,
        le=86400,
        validation_alias="OPEN_ALM_AI_CONVERSATION_RUN_LOCK_TTL_SECONDS",
    )
    ai_local_tool_calling_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_LOCAL_TOOL_CALLING_ENABLED",
    )
    ai_mcp_bridge_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_MCP_BRIDGE_ENABLED",
    )
    ai_write_tools_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_WRITE_TOOLS_ENABLED",
    )
    ai_runtime_graph_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_RUNTIME_GRAPH_ENABLED",
    )
    ai_runtime_graph_execution_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_RUNTIME_GRAPH_EXECUTION_ENABLED",
    )
    ai_runtime_shadow_write_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_AI_RUNTIME_SHADOW_WRITE_ENABLED",
    )
    ai_runtime_trace_payload_max_bytes: int = Field(
        default=32768,
        ge=1024,
        le=1048576,
        validation_alias="OPEN_ALM_AI_RUNTIME_TRACE_PAYLOAD_MAX_BYTES",
    )
    ai_runtime_retention_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        validation_alias="OPEN_ALM_AI_RUNTIME_RETENTION_DAYS",
    )
    ai_external_llm_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_LLM_ENABLED",
    )
    ai_external_planning_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_PLANNING_ENABLED",
    )
    ai_external_reasoning_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_REASONING_ENABLED",
    )
    ai_external_quality_review_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_QUALITY_REVIEW_ENABLED",
    )
    ai_external_search_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_SEARCH_ENABLED",
    )
    ai_external_planner_execution_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_PLANNER_EXECUTION_ENABLED",
    )
    ai_external_search_execution_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_AI_EXTERNAL_SEARCH_EXECUTION_ENABLED",
    )
    ai_external_planner_execution_adapter: str = Field(
        default="mock",
        validation_alias="OPEN_ALM_AI_EXTERNAL_PLANNER_EXECUTION_ADAPTER",
    )
    ai_external_search_execution_adapter: str = Field(
        default="mock",
        validation_alias="OPEN_ALM_AI_EXTERNAL_SEARCH_EXECUTION_ADAPTER",
    )
    ai_default_external_llm_provider: str = Field(
        default="openai",
        validation_alias="OPEN_ALM_AI_DEFAULT_EXTERNAL_LLM_PROVIDER",
    )
    ai_default_external_search_provider: str = Field(
        default="openai",
        validation_alias="OPEN_ALM_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER",
    )
    ai_allowed_external_providers: str = Field(
        default="openai,anthropic,gemini,kipris",
        validation_alias="OPEN_ALM_AI_ALLOWED_EXTERNAL_PROVIDERS",
    )
    ai_agent_max_turns: int = Field(
        default=8,
        ge=1,
        le=32,
        validation_alias="OPEN_ALM_AI_AGENT_MAX_TURNS",
    )
    ai_agent_max_tool_calls: int = Field(
        default=16,
        ge=1,
        le=64,
        validation_alias="OPEN_ALM_AI_AGENT_MAX_TOOL_CALLS",
    )
    ai_agent_max_consecutive_tool_errors: int = Field(
        default=3,
        ge=1,
        le=16,
        validation_alias="OPEN_ALM_AI_AGENT_MAX_CONSECUTIVE_TOOL_ERRORS",
    )
    rag_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_RAG_ENABLED",
    )
    files_retrieval_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_FILES_RETRIEVAL_ENABLED",
    )
    retrieval_unified_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_RETRIEVAL_UNIFIED_ENABLED",
    )
    rag_query_timeout_ms: int = Field(
        default=210000,
        ge=100,
        le=600000,
        validation_alias="OPEN_ALM_RAG_QUERY_TIMEOUT_MS",
    )
    rag_qdrant_url: str = Field(
        default="",
        validation_alias="OPEN_ALM_RAG_QDRANT_URL",
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias="OPEN_ALM_RAG_QDRANT_API_KEY",
    )
    rag_qdrant_collection_prefix: str = Field(
        default="open-alm-dev-rag",
        validation_alias="OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX",
    )
    rag_vector_index_provider: str = Field(
        default="fake",
        validation_alias="OPEN_ALM_RAG_VECTOR_INDEX_PROVIDER",
    )
    rag_embedding_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_PROVIDER",
    )
    rag_ocr_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_ALM_RAG_OCR_PROVIDER",
    )
    rag_rerank_provider: str = Field(
        default="inference_gateway",
        validation_alias="OPEN_ALM_RAG_RERANK_PROVIDER",
    )
    rag_rerank_candidate_k: int = Field(
        default=80,
        ge=1,
        le=100,
        validation_alias="OPEN_ALM_RAG_RERANK_CANDIDATE_K",
    )
    rag_preload_on_startup: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_RAG_PRELOAD_ON_STARTUP",
    )
    rag_fail_startup_on_preload_error: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_RAG_FAIL_STARTUP_ON_PRELOAD_ERROR",
    )
    rag_job_processing_lease_seconds: int = Field(
        default=2100,
        ge=60,
        le=7200,
        validation_alias="OPEN_ALM_RAG_JOB_PROCESSING_LEASE_SECONDS",
    )
    rag_local_embedding_model: str = Field(
        default="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_MODEL",
    )
    rag_local_embedding_revision: str | None = Field(
        default="55ec6e9358a56d56af759bc8372e970caf8c305f",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_REVISION",
    )
    rag_local_embedding_device: str = Field(
        default="auto",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_DEVICE",
    )
    rag_local_embedding_dtype: str = Field(
        default="bfloat16",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_DTYPE",
    )
    rag_local_embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="OPEN_ALM_RAG_EMBEDDING_BATCH_SIZE",
    )
    rag_local_embedding_max_seq_length: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="OPEN_ALM_RAG_EMBEDDING_MAX_SEQ_LENGTH",
    )
    rag_local_embedding_normalize: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_RAG_EMBEDDING_NORMALIZE",
    )
    rag_local_embedding_query_prompt_name: str = Field(
        default="query",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_QUERY_PROMPT_NAME",
    )
    rag_local_embedding_query_prefix: str = Field(
        default="",
        validation_alias="OPEN_ALM_RAG_EMBEDDING_QUERY_PREFIX",
    )
    rag_local_embedding_trust_remote_code: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_RAG_EMBEDDING_TRUST_REMOTE_CODE",
    )
    rag_local_reranker_model: str = Field(
        default="dragonkue/bge-reranker-v2-m3-ko",
        validation_alias="OPEN_ALM_RAG_RERANKER_MODEL",
    )
    rag_local_reranker_revision: str | None = Field(
        default="2aca5884ecac490192af9ebd86836d9073d826cd",
        validation_alias="OPEN_ALM_RAG_RERANKER_REVISION",
    )
    rag_local_reranker_device: str = Field(
        default="auto",
        validation_alias="OPEN_ALM_RAG_RERANKER_DEVICE",
    )
    rag_local_reranker_dtype: str = Field(
        default="bfloat16",
        validation_alias="OPEN_ALM_RAG_RERANKER_DTYPE",
    )
    rag_local_reranker_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="OPEN_ALM_RAG_RERANKER_BATCH_SIZE",
    )
    rag_local_reranker_max_length: int = Field(
        default=512,
        ge=128,
        le=8192,
        validation_alias="OPEN_ALM_RAG_RERANKER_MAX_LENGTH",
    )
    rag_local_reranker_trust_remote_code: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_RAG_RERANKER_TRUST_REMOTE_CODE",
    )
    rag_docling_force_ocr: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_RAG_DOCLING_FORCE_OCR",
    )
    rag_docling_ocr_engine: str = Field(
        default="easyocr",
        validation_alias="OPEN_ALM_RAG_DOCLING_OCR_ENGINE",
    )
    rag_docling_ocr_langs: str = Field(
        default="ko,en",
        validation_alias="OPEN_ALM_RAG_DOCLING_OCR_LANGS",
    )
    rag_docling_min_text_chars: int = Field(
        default=128,
        ge=0,
        le=10000,
        validation_alias="OPEN_ALM_RAG_DOCLING_MIN_TEXT_CHARS",
    )
    rag_vision_ocr_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_RAG_VISION_OCR_ENABLED",
    )
    rag_vision_ocr_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias="OPEN_ALM_RAG_VISION_OCR_TIMEOUT_SECONDS",
    )
    rag_vision_ocr_max_pages: int = Field(
        default=2,
        ge=1,
        le=20,
        validation_alias="OPEN_ALM_RAG_VISION_OCR_MAX_PAGES",
    )
    rag_vision_ocr_dpi: int = Field(
        default=160,
        ge=72,
        le=300,
        validation_alias="OPEN_ALM_RAG_VISION_OCR_DPI",
    )
    rag_vision_ocr_max_new_tokens: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="OPEN_ALM_RAG_VISION_OCR_MAX_NEW_TOKENS",
    )
    # PLM Oracle read-only integration.
    plm_oracle_host: str = Field(
        default="",
        validation_alias="OPEN_ALM_PLM_ORACLE_HOST",
    )
    plm_oracle_port: int = Field(
        default=1521,
        ge=1,
        le=65535,
        validation_alias="OPEN_ALM_PLM_ORACLE_PORT",
    )
    plm_oracle_sid: str = Field(
        default="",
        validation_alias="OPEN_ALM_PLM_ORACLE_SID",
    )
    plm_oracle_user: str = Field(
        default="",
        validation_alias="OPEN_ALM_PLM_ORACLE_USER",
    )
    plm_oracle_password: str = Field(
        default="",
        validation_alias="OPEN_ALM_PLM_ORACLE_PASSWORD",
    )
    plm_ojdbc_jar: str = Field(
        default="",
        validation_alias="OPEN_ALM_PLM_OJDBC_JAR",
    )
    # Patent (AI 특허 작성) — KIPRIS (Korean patent office) search API.
    patent_kipris_api_key: str = Field(
        default="",
        validation_alias="OPEN_ALM_PATENT_KIPRIS_API_KEY",
    )
    patent_kipris_base_url: str = Field(
        default="https://plus.kipris.or.kr/kipo-api/kipi/patUtiModInfoSearchSevice",
        validation_alias="OPEN_ALM_PATENT_KIPRIS_BASE_URL",
    )
    # Image generation — wizard-driven image API via the OpenAI Agents SDK.
    image_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_IMAGE_ENABLED",
    )
    image_max_reference_uploads: int = Field(
        default=4,
        ge=1,
        le=12,
        validation_alias="OPEN_ALM_IMAGE_MAX_REFS",
    )
    image_reference_max_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=64 * 1024,
        le=64 * 1024 * 1024,
        validation_alias="OPEN_ALM_IMAGE_REFERENCE_MAX_BYTES",
    )
    otel_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_OTEL_ENABLED",
    )
    otel_console_exporter: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_OTEL_CONSOLE_EXPORTER",
    )
    otel_otlp_exporter_enabled: bool = Field(
        default=False,
        validation_alias="OPEN_ALM_OTEL_OTLP_EXPORTER_ENABLED",
    )
    otel_metrics_export_interval_ms: int = Field(
        default=60000,
        ge=1000,
        le=300000,
        validation_alias="OPEN_ALM_OTEL_METRICS_EXPORT_INTERVAL_MS",
    )
    event_loop_lag_warn_ms: int = Field(
        default=2000,
        ge=100,
        le=60000,
        validation_alias="OPEN_ALM_API_EVENT_LOOP_LAG_WARN_MS",
    )
    event_loop_lag_interval_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        validation_alias="OPEN_ALM_API_EVENT_LOOP_LAG_INTERVAL_SECONDS",
    )

    model_config = SettingsConfigDict(
        env_prefix="OPEN_ALM_API_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _validate_runtime_config(self) -> "Settings":
        self.environment = normalize_runtime_environment(self.environment)
        self.env_profile = self.env_profile.strip().lower()
        self.open_alm_desktop_update_dirs = open_alm_desktop_update_dir_values(_settings_env_values())
        self.frontend_dist_dir = self.frontend_dist_dir.strip() or DEFAULT_FRONTEND_DIST_DIR
        self.dm_attachment_signing_key = _normalize_dm_attachment_signing_key(
            self.dm_attachment_signing_key,
            environment=self.environment,
        )
        self.llm_external_allowed_providers = _normalize_external_provider_list_text(
            self.llm_external_allowed_providers,
        )
        self.opf_checkpoint = self.opf_checkpoint.strip() or DEFAULT_OPF_CHECKPOINT
        self.opf_cache_dir = self.opf_cache_dir.strip() or str(
            WORKSPACE_ROOT.parent / ".cache" / "opf",
        )
        self.opf_device = "cpu"
        self.opf_service_base_url = self.opf_service_base_url.strip().rstrip("/")
        self.ai_allowed_external_providers = _normalize_external_provider_list_text(
            self.ai_allowed_external_providers,
        )
        self.ai_default_external_llm_provider = _normalize_external_provider_text(
            self.ai_default_external_llm_provider,
        )
        self.ai_default_external_search_provider = _normalize_external_provider_text(
            self.ai_default_external_search_provider,
        )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def _normalize_dm_attachment_signing_key(value: str, *, environment: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        normalized = DEFAULT_DM_ATTACHMENT_SIGNING_KEY
    if (
        is_production_like_environment(environment)
        and normalized == DEFAULT_DM_ATTACHMENT_SIGNING_KEY
    ):
        raise ValueError("OPEN_ALM_DM_ATTACHMENT_SIGNING_KEY must be set for preview/production.")
    return normalized


def _normalize_external_provider_text(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_external_provider_list_text(value: str) -> str:
    providers: list[str] = []
    for raw_provider in str(value or "").split(","):
        normalized = _normalize_external_provider_text(raw_provider)
        if not normalized:
            continue
        if normalized not in providers:
            providers.append(normalized)
    return ",".join(providers)
