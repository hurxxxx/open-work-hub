from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive

JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class AiSecurityDataProtectionSettings(Base):
    """Singleton settings for external AI egress data-protection controls."""

    __tablename__ = "ai_security_data_protection_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enforcement_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    enforcement_disabled_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    custom_block_terms_json: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=True,
    )
    blocker_actions_json: Mapped[dict[str, str] | None] = mapped_column(
        JSONB_COMPAT,
        default=dict,
        nullable=True,
    )
    external_app_actions_json: Mapped[dict[str, dict[str, str]] | None] = mapped_column(
        JSONB_COMPAT,
        default=dict,
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )


class AiSecurityPolicyRule(Base):
    """Scoped policy overlay for AI Gateway and external provider egress."""

    __tablename__ = "ai_security_policy_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    app_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_kind: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    task_kinds_json: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=True,
    )
    capability: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    effect: Mapped[str] = mapped_column(String(32), default="inherit", nullable=False, index=True)
    custom_block_terms_json: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    @property
    def custom_block_terms(self) -> list[str]:
        value = self.custom_block_terms_json
        return value if isinstance(value, list) else []


class AiSecurityExternalTransferException(Base):
    """Scoped exception that allows specific soft blockers to use external AI."""

    __tablename__ = "ai_security_external_transfer_exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"), nullable=True, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    app_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_kind: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    task_kinds_json: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=True,
    )
    capability: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    allowed_blocker_types_json: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        default=list,
        nullable=True,
    )
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    @property
    def allowed_blocker_types(self) -> list[str]:
        value = self.allowed_blocker_types_json
        return value if isinstance(value, list) else []


class AiSecurityDetectedValue(Base):
    """Sensitive values or detector-only counts observed during AI security checks."""

    __tablename__ = "ai_security_detected_values"
    __table_args__ = (
        Index(
            "ix_ai_security_detected_values_period_type_hash",
            "created_at",
            "entity_type",
            "value_hash",
        ),
        Index(
            "ix_ai_security_detected_values_period_detector",
            "created_at",
            "detector",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audit_log_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_logs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    app_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    task_kind: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    capability: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    detector: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    blocker_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    detected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
