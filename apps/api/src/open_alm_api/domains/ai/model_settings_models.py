from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class AiModelProviderConfig(Base):
    __tablename__ = "ai_model_provider_configs"

    provider_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        info={"secret": True},
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_model_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AiModelCatalogEntry(Base):
    __tablename__ = "ai_model_catalog_entries"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'discovered')",
            name="ck_ai_model_catalog_entries_source",
        ),
        CheckConstraint(
            "discovery_status IN ('active', 'stale')",
            name="ck_ai_model_catalog_entries_discovery_status",
        ),
        UniqueConstraint(
            "provider_id",
            "model_key",
            name="uq_ai_model_catalog_entries_provider_model",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_id: Mapped[str] = mapped_column(
        ForeignKey("ai_model_provider_configs.provider_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    model_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(16),
        default="manual",
        nullable=False,
    )
    discovery_status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    @property
    def capabilities(self) -> tuple[str, ...]:
        value = self.capabilities_json
        return tuple(item for item in value if isinstance(item, str))


class AiModelRouteOverride(Base):
    __tablename__ = "ai_model_route_overrides"
    __table_args__ = (
        UniqueConstraint("workload_id", name="uq_ai_model_route_overrides_workload"),
        CheckConstraint(
            "route_mode IN ('local', 'external')",
            name="ck_ai_model_route_overrides_route_mode",
        ),
        CheckConstraint(
            "local_max_output_tokens IS NULL OR "
            "(local_max_output_tokens BETWEEN 1024 AND 65536 AND "
            "local_max_output_tokens % 1024 = 0)",
            name="ck_ai_model_route_overrides_local_max_output_tokens",
        ),
        CheckConstraint(
            "external_max_output_tokens IS NULL OR "
            "(external_max_output_tokens BETWEEN 1024 AND 65536 AND "
            "external_max_output_tokens % 1024 = 0)",
            name="ck_ai_model_route_overrides_external_max_output_tokens",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workload_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    route_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_model_provider_configs.provider_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    model_ids_json: Mapped[dict[str, str]] = mapped_column(
        JSONB_COMPAT,
        default=dict,
        nullable=False,
    )
    local_max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    @property
    def model_ids(self) -> dict[str, str]:
        value = self.model_ids_json
        if not isinstance(value, dict):
            return {}
        return {
            str(role): str(model_id)
            for role, model_id in value.items()
            if str(role).strip() and str(model_id).strip()
        }


__all__ = [
    "AiModelCatalogEntry",
    "AiModelProviderConfig",
    "AiModelRouteOverride",
]
