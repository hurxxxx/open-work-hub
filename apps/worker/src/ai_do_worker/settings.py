from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
        validation_alias="AI_DO_POSTGRES_DSN",
    )
    queue_group: str = Field(
        default="all",
        validation_alias="AI_DO_WORKER_QUEUE_GROUP",
    )
    env_profile: str = Field(
        default="local",
        validation_alias="AI_DO_ENV_PROFILE",
    )
    minio_endpoint: str = Field(
        default="http://127.0.0.1:9000",
        validation_alias="AI_DO_MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(
        default="minioadmin",
        validation_alias="AI_DO_MINIO_ACCESS_KEY",
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        validation_alias="AI_DO_MINIO_SECRET_KEY",
    )
    minio_bucket: str = Field(
        default="ai-do-portal",
        validation_alias="AI_DO_MINIO_BUCKET",
    )
    asr_backend: str = Field(
        default="inference_gateway",
        validation_alias="AI_DO_API_ASR_BACKEND",
    )
    llm_external_allowed_providers: str = Field(
        default="openai,anthropic,gemini",
        validation_alias="AI_DO_LLM_EXTERNAL_ALLOWED_PROVIDERS",
    )
    ai_allowed_external_providers: str = Field(
        default="openai,anthropic,gemini,kipris",
        validation_alias="AI_DO_AI_ALLOWED_EXTERNAL_PROVIDERS",
    )
    ai_default_external_llm_provider: str = Field(
        default="openai",
        validation_alias="AI_DO_AI_DEFAULT_EXTERNAL_LLM_PROVIDER",
    )
    ai_default_external_search_provider: str = Field(
        default="openai",
        validation_alias="AI_DO_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER",
    )
    ai_external_llm_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_LLM_ENABLED",
    )
    ai_external_planner_execution_adapter: str = Field(
        default="mock",
        validation_alias="AI_DO_AI_EXTERNAL_PLANNER_EXECUTION_ADAPTER",
    )
    ai_external_planner_execution_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_PLANNER_EXECUTION_ENABLED",
    )
    ai_external_planning_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_PLANNING_ENABLED",
    )
    ai_external_quality_review_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_QUALITY_REVIEW_ENABLED",
    )
    ai_external_reasoning_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_REASONING_ENABLED",
    )
    ai_external_search_execution_adapter: str = Field(
        default="mock",
        validation_alias="AI_DO_AI_EXTERNAL_SEARCH_EXECUTION_ADAPTER",
    )
    ai_external_search_execution_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_AI_EXTERNAL_SEARCH_EXECUTION_ENABLED",
    )
    rag_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_RAG_ENABLED",
    )
    files_retrieval_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_FILES_RETRIEVAL_ENABLED",
    )
    rag_query_timeout_ms: int = Field(
        default=210000,
        ge=100,
        le=600000,
        validation_alias="AI_DO_RAG_QUERY_TIMEOUT_MS",
    )
    rag_qdrant_url: str = Field(
        default="",
        validation_alias="AI_DO_RAG_QDRANT_URL",
    )
    rag_qdrant_api_key: str = Field(
        default="",
        validation_alias="AI_DO_RAG_QDRANT_API_KEY",
    )
    rag_qdrant_collection_prefix: str = Field(
        default="ai-do-dev-rag",
        validation_alias="AI_DO_RAG_QDRANT_COLLECTION_PREFIX",
    )
    rag_vector_index_provider: str = Field(
        default="fake",
        validation_alias="AI_DO_RAG_VECTOR_INDEX_PROVIDER",
    )
    rag_embedding_provider: str = Field(
        default="inference_gateway",
        validation_alias="AI_DO_RAG_EMBEDDING_PROVIDER",
    )
    rag_ocr_provider: str = Field(
        default="inference_gateway",
        validation_alias="AI_DO_RAG_OCR_PROVIDER",
    )
    rag_rerank_provider: str = Field(
        default="inference_gateway",
        validation_alias="AI_DO_RAG_RERANK_PROVIDER",
    )
    rag_rerank_candidate_k: int = Field(
        default=80,
        ge=1,
        le=100,
        validation_alias="AI_DO_RAG_RERANK_CANDIDATE_K",
    )
    rag_preload_on_startup: bool = Field(
        default=True,
        validation_alias="AI_DO_RAG_PRELOAD_ON_STARTUP",
    )
    rag_fail_startup_on_preload_error: bool = Field(
        default=False,
        validation_alias="AI_DO_RAG_FAIL_STARTUP_ON_PRELOAD_ERROR",
    )
    inference_gateway_base_url: str = Field(
        default="http://127.0.0.1:18080",
        validation_alias="AI_DO_INFERENCE_GATEWAY_BASE_URL",
    )
    inference_gateway_api_key: str = Field(
        default="local",
        validation_alias="AI_DO_INFERENCE_GATEWAY_API_KEY",
    )
    rag_local_embedding_model: str = Field(
        default="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        validation_alias="AI_DO_RAG_EMBEDDING_MODEL",
    )
    rag_local_embedding_revision: str | None = Field(
        default="55ec6e9358a56d56af759bc8372e970caf8c305f",
        validation_alias="AI_DO_RAG_EMBEDDING_REVISION",
    )
    rag_local_embedding_device: str = Field(
        default="auto",
        validation_alias="AI_DO_RAG_EMBEDDING_DEVICE",
    )
    rag_local_embedding_dtype: str = Field(
        default="bfloat16",
        validation_alias="AI_DO_RAG_EMBEDDING_DTYPE",
    )
    rag_local_embedding_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="AI_DO_RAG_EMBEDDING_BATCH_SIZE",
    )
    rag_local_embedding_max_seq_length: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="AI_DO_RAG_EMBEDDING_MAX_SEQ_LENGTH",
    )
    rag_local_embedding_normalize: bool = Field(
        default=True,
        validation_alias="AI_DO_RAG_EMBEDDING_NORMALIZE",
    )
    rag_local_embedding_query_prompt_name: str = Field(
        default="query",
        validation_alias="AI_DO_RAG_EMBEDDING_QUERY_PROMPT_NAME",
    )
    rag_local_embedding_query_prefix: str = Field(
        default="",
        validation_alias="AI_DO_RAG_EMBEDDING_QUERY_PREFIX",
    )
    rag_local_embedding_trust_remote_code: bool = Field(
        default=False,
        validation_alias="AI_DO_RAG_EMBEDDING_TRUST_REMOTE_CODE",
    )
    rag_local_reranker_model: str = Field(
        default="dragonkue/bge-reranker-v2-m3-ko",
        validation_alias="AI_DO_RAG_RERANKER_MODEL",
    )
    rag_local_reranker_revision: str | None = Field(
        default="2aca5884ecac490192af9ebd86836d9073d826cd",
        validation_alias="AI_DO_RAG_RERANKER_REVISION",
    )
    rag_local_reranker_device: str = Field(
        default="auto",
        validation_alias="AI_DO_RAG_RERANKER_DEVICE",
    )
    rag_local_reranker_dtype: str = Field(
        default="bfloat16",
        validation_alias="AI_DO_RAG_RERANKER_DTYPE",
    )
    rag_local_reranker_batch_size: int = Field(
        default=16,
        ge=1,
        le=256,
        validation_alias="AI_DO_RAG_RERANKER_BATCH_SIZE",
    )
    rag_local_reranker_max_length: int = Field(
        default=512,
        ge=128,
        le=8192,
        validation_alias="AI_DO_RAG_RERANKER_MAX_LENGTH",
    )
    rag_local_reranker_trust_remote_code: bool = Field(
        default=False,
        validation_alias="AI_DO_RAG_RERANKER_TRUST_REMOTE_CODE",
    )
    rag_docling_force_ocr: bool = Field(
        default=False,
        validation_alias="AI_DO_RAG_DOCLING_FORCE_OCR",
    )
    rag_docling_ocr_engine: str = Field(
        default="easyocr",
        validation_alias="AI_DO_RAG_DOCLING_OCR_ENGINE",
    )
    rag_docling_ocr_langs: str = Field(
        default="ko,en",
        validation_alias="AI_DO_RAG_DOCLING_OCR_LANGS",
    )
    rag_docling_min_text_chars: int = Field(
        default=128,
        ge=0,
        le=10000,
        validation_alias="AI_DO_RAG_DOCLING_MIN_TEXT_CHARS",
    )
    rag_vision_ocr_enabled: bool = Field(
        default=True,
        validation_alias="AI_DO_RAG_VISION_OCR_ENABLED",
    )
    rag_vision_ocr_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias="AI_DO_RAG_VISION_OCR_TIMEOUT_SECONDS",
    )
    rag_vision_ocr_max_pages: int = Field(
        default=2,
        ge=1,
        le=20,
        validation_alias="AI_DO_RAG_VISION_OCR_MAX_PAGES",
    )
    rag_vision_ocr_dpi: int = Field(
        default=160,
        ge=72,
        le=300,
        validation_alias="AI_DO_RAG_VISION_OCR_DPI",
    )
    rag_vision_ocr_max_new_tokens: int = Field(
        default=1024,
        ge=128,
        le=8192,
        validation_alias="AI_DO_RAG_VISION_OCR_MAX_NEW_TOKENS",
    )
    rag_backfill_batch_size: int = Field(
        default=25,
        ge=1,
        le=500,
        validation_alias="AI_DO_RAG_BACKFILL_BATCH_SIZE",
    )
    rag_backfill_throttle_ms: int = Field(
        default=50,
        ge=0,
        le=60000,
        validation_alias="AI_DO_RAG_BACKFILL_THROTTLE_MS",
    )
    rag_job_max_attempts: int = Field(
        default=3,
        ge=1,
        le=20,
        validation_alias="AI_DO_RAG_JOB_MAX_ATTEMPTS",
    )
    rag_job_retry_backoff_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        validation_alias="AI_DO_RAG_JOB_RETRY_BACKOFF_SECONDS",
    )
    rag_job_processing_lease_seconds: int = Field(
        default=2100,
        ge=60,
        le=7200,
        validation_alias="AI_DO_RAG_JOB_PROCESSING_LEASE_SECONDS",
    )
    mail_sync_processing_lease_seconds: int = Field(
        default=900,
        ge=60,
        le=7200,
        validation_alias="AI_DO_MAIL_SYNC_PROCESSING_LEASE_SECONDS",
    )
    hr_groupware_sync_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_HR_GROUPWARE_SYNC_ENABLED",
    )
    hr_groupware_db_host: str = Field(
        default="",
        validation_alias="AI_DO_HR_GROUPWARE_DB_HOST",
    )
    hr_groupware_db_port: int = Field(
        default=1433,
        ge=1,
        le=65535,
        validation_alias="AI_DO_HR_GROUPWARE_DB_PORT",
    )
    hr_groupware_db_name: str = Field(
        default="dw_visitor",
        validation_alias="AI_DO_HR_GROUPWARE_DB_NAME",
    )
    hr_groupware_db_username: str = Field(
        default="",
        validation_alias="AI_DO_HR_GROUPWARE_DB_USERNAME",
    )
    hr_groupware_db_password: str = Field(
        default="",
        validation_alias="AI_DO_HR_GROUPWARE_DB_PASSWORD",
    )
    hr_groupware_db_timeout_seconds: int = Field(
        default=15,
        ge=1,
        le=120,
        validation_alias="AI_DO_HR_GROUPWARE_DB_TIMEOUT_SECONDS",
    )
    hr_groupware_sync_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="AI_DO_HR_GROUPWARE_SYNC_HOUR",
    )
    hr_groupware_sync_minute: int = Field(
        default=10,
        ge=0,
        le=59,
        validation_alias="AI_DO_HR_GROUPWARE_SYNC_MINUTE",
    )
    hr_groupware_sync_timezone: str = Field(
        default="Asia/Seoul",
        validation_alias="AI_DO_HR_GROUPWARE_SYNC_TIMEZONE",
    )
    erp_db_ip: str = Field(
        default="",
        validation_alias="AI_DO_ERP_DB_IP",
    )
    erp_db_port: int = Field(
        default=1433,
        ge=1,
        le=65535,
        validation_alias="AI_DO_ERP_DB_PORT",
    )
    erp_db_name: str = Field(
        default="",
        validation_alias="AI_DO_ERP_DB_NAME",
    )
    erp_db_id: str = Field(
        default="",
        validation_alias="AI_DO_ERP_DB_ID",
    )
    erp_db_pw: str = Field(
        default="",
        validation_alias="AI_DO_ERP_DB_PW",
    )
    erp_db_timeout_seconds: int = Field(
        default=15,
        ge=1,
        le=120,
        validation_alias="AI_DO_ERP_DB_TIMEOUT_SECONDS",
    )
    erp_hr_snapshot_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_ERP_HR_SNAPSHOT_ENABLED",
    )
    erp_hr_snapshot_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="AI_DO_ERP_HR_SNAPSHOT_HOUR",
    )
    erp_hr_snapshot_minute: int = Field(
        default=20,
        ge=0,
        le=59,
        validation_alias="AI_DO_ERP_HR_SNAPSHOT_MINUTE",
    )
    hr_master_sync_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_HR_MASTER_SYNC_ENABLED",
    )
    hr_master_sync_hour: int = Field(
        default=3,
        ge=0,
        le=23,
        validation_alias="AI_DO_HR_MASTER_SYNC_HOUR",
    )
    hr_master_sync_minute: int = Field(
        default=30,
        ge=0,
        le=59,
        validation_alias="AI_DO_HR_MASTER_SYNC_MINUTE",
    )
    naver_client_id: str = Field(
        default="",
        validation_alias="AI_DO_NAVER_CLIENT_ID",
    )
    naver_client_secret: str = Field(
        default="",
        validation_alias="AI_DO_NAVER_CLIENT_SECRET",
    )
    news_crawl_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_NEWS_CRAWL_ENABLED",
    )
    news_crawl_every_hours: int = Field(
        default=2,
        ge=1,
        le=24,
        validation_alias="AI_DO_NEWS_CRAWL_EVERY_HOURS",
    )
    news_crawl_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="AI_DO_NEWS_CRAWL_MINUTE",
    )
    qna_board_crawl_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_QNA_BOARD_CRAWL_ENABLED",
    )
    # Board title/category to keep from the groupware web board list.
    qna_board_category: str = Field(
        default="주요공지사항(관리팀)",
        validation_alias="AI_DO_QNA_BOARD_CATEGORY",
    )
    # Legacy board menu number kept for env compatibility; web crawling filters
    # by qna_board_category.
    qna_board_mnu_num: int = Field(
        default=10,
        ge=0,
        validation_alias="AI_DO_QNA_BOARD_MNU_NUM",
    )
    # Groupware web access for board metadata, notice body, and attachments.
    qna_board_web_base_url: str = Field(
        default="http://gw.dwdcc.co.kr",
        validation_alias="AI_DO_QNA_BOARD_WEB_BASE_URL",
    )
    qna_board_web_username: str = Field(
        default="",
        validation_alias="AI_DO_QNA_BOARD_WEB_USERNAME",
    )
    qna_board_web_password: str = Field(
        default="",
        validation_alias="AI_DO_QNA_BOARD_WEB_PASSWORD",
    )
    qna_board_max_posts: int = Field(
        default=20,
        ge=1,
        le=200,
        validation_alias="AI_DO_QNA_BOARD_MAX_POSTS",
    )
    qna_board_attachment_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        validation_alias="AI_DO_QNA_BOARD_ATTACHMENT_MAX_BYTES",
    )
    qna_board_attachments_max_total_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1024,
        le=1024 * 1024 * 1024,
        validation_alias="AI_DO_QNA_BOARD_ATTACHMENTS_MAX_TOTAL_BYTES",
    )
    qna_board_sync_hour: int = Field(
        default=7,
        ge=0,
        le=23,
        validation_alias="AI_DO_QNA_BOARD_SYNC_HOUR",
    )
    qna_board_sync_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="AI_DO_QNA_BOARD_SYNC_MINUTE",
    )
    industry_report_crawl_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_INDUSTRY_REPORT_CRAWL_ENABLED",
    )
    industry_report_crawl_hour: int = Field(
        default=7,
        ge=0,
        le=23,
        validation_alias="AI_DO_INDUSTRY_REPORT_CRAWL_HOUR",
    )
    industry_report_crawl_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        validation_alias="AI_DO_INDUSTRY_REPORT_CRAWL_MINUTE",
    )
    industry_report_crawl_max_file_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1024,
        le=512 * 1024 * 1024,
        validation_alias="AI_DO_INDUSTRY_REPORT_CRAWL_MAX_FILE_BYTES",
    )
    opensearch_url: str = Field(
        default="http://127.0.0.1:59210",
        validation_alias="AI_DO_OPENSEARCH_URL",
    )
    opensearch_index_prefix: str = Field(
        default="ai-do-dev",
        validation_alias="AI_DO_OPENSEARCH_INDEX_PREFIX",
    )
    keyword_search_backend: str = Field(
        default="opensearch",
        validation_alias="AI_DO_KEYWORD_SEARCH_BACKEND",
    )
    image_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_IMAGE_ENABLED",
    )
    image_max_reference_uploads: int = Field(
        default=4,
        ge=1,
        le=12,
        validation_alias="AI_DO_IMAGE_MAX_REFS",
    )
    image_reference_max_bytes: int = Field(
        default=8 * 1024 * 1024,
        ge=64 * 1024,
        le=64 * 1024 * 1024,
        validation_alias="AI_DO_IMAGE_REFERENCE_MAX_BYTES",
    )
    image_request_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        le=3600,
        validation_alias="AI_DO_IMAGE_REQUEST_TIMEOUT_SECONDS",
    )

    otel_enabled: bool = Field(
        default=True,
        validation_alias="AI_DO_OTEL_ENABLED",
    )
    otel_console_exporter: bool = Field(
        default=False,
        validation_alias="AI_DO_OTEL_CONSOLE_EXPORTER",
    )
    otel_otlp_exporter_enabled: bool = Field(
        default=False,
        validation_alias="AI_DO_OTEL_OTLP_EXPORTER_ENABLED",
    )
    otel_metrics_export_interval_ms: int = Field(
        default=60000,
        ge=1000,
        le=300000,
        validation_alias="AI_DO_OTEL_METRICS_EXPORT_INTERVAL_MS",
    )

    model_config = SettingsConfigDict(
        env_prefix="AI_DO_WORKER_",
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
