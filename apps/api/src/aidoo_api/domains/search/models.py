from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aidoo_api.core.db import Base
from aidoo_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class SearchIndexJob(Base):
    __tablename__ = "search_index_jobs"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('doc','meeting','pms_issue','planner_event')",
            name="ck_search_index_jobs_entity_type",
        ),
        CheckConstraint(
            "operation IN ('upsert','delete')",
            name="ck_search_index_jobs_operation",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_search_index_jobs_status",
        ),
        Index(
            "ix_search_index_jobs_workspace_status_retry",
            "workspace_id",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_search_index_jobs_entity_status",
            "entity_type",
            "entity_id",
            "status",
        ),
        Index(
            "uq_search_index_jobs_pending_entity",
            "workspace_id",
            "entity_type",
            "entity_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="upsert",
        server_default=text("'upsert'"),
    )
    trace_context: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
