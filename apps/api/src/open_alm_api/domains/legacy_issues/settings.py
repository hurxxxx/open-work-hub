from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from open_alm_api.core.settings import ENV_FILE


class LegacyIssueSettings(BaseSettings):
    ai_semantic_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_SEMANTIC_ENABLED",
    )
    ai_index_embeddings_on_write: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_INDEX_EMBEDDINGS_ON_WRITE",
    )
    ai_embedding_dimensions: int = Field(
        default=1024,
        ge=1,
        le=4096,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_EMBEDDING_DIMENSIONS",
    )
    ai_max_sync_embedding_chunks: int = Field(
        default=300,
        ge=0,
        le=5000,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_MAX_SYNC_EMBEDDING_CHUNKS",
    )
    ai_default_evidence_limit: int = Field(
        default=12,
        ge=1,
        le=50,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_DEFAULT_EVIDENCE_LIMIT",
    )
    ai_attachment_index_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_INDEX_ENABLED",
    )
    ai_attachment_index_max_chunks: int = Field(
        default=120,
        ge=1,
        le=1000,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_INDEX_MAX_CHUNKS",
    )
    ai_attachment_index_vlm_always: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_INDEX_VLM_ALWAYS",
    )
    ai_attachment_index_vision_max_pages: int = Field(
        default=0,
        ge=0,
        le=1000,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_INDEX_VISION_MAX_PAGES",
    )
    ai_attachment_summary_enabled: bool = Field(
        default=True,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_SUMMARY_ENABLED",
    )
    ai_attachment_summary_input_max_chars: int = Field(
        default=60000,
        ge=1000,
        le=250000,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_SUMMARY_INPUT_MAX_CHARS",
    )
    ai_attachment_summary_max_tokens: int = Field(
        default=2500,
        ge=256,
        le=12000,
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_SUMMARY_MAX_TOKENS",
    )
    ai_attachment_summary_model: str = Field(
        default="",
        validation_alias="OPEN_ALM_LEGACY_ISSUE_AI_ATTACHMENT_SUMMARY_MODEL",
    )

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_legacy_issue_settings() -> LegacyIssueSettings:
    return LegacyIssueSettings()
