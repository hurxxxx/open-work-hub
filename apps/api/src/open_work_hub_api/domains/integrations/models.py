from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


class PlatformApiKey(Base):
    __tablename__ = "platform_api_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_platform_api_keys_status",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_platform_api_keys_name",
        ),
        CheckConstraint(
            "substr(key_prefix, 1, 7) = 'owh_pk_'",
            name="ck_platform_api_keys_prefix",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_by_user_id IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_platform_api_keys_revocation",
        ),
        Index("ix_platform_api_keys_status_created", "status", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="active",
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
