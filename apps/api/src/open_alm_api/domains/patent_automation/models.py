from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import User, utcnow_naive


# Same portable JSONB type the legacy_issues domain uses: real JSONB on
# Postgres, plain JSON on the SQLite test database.
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")

# Single logical dataset for the patent-status workbook; kept as a column so the
# revision machinery matches legacy_issues and leaves room for future datasets.
PATENT_STATUS_DATASET_KEY = "patent_status"


class PatentDataRevision(Base):
    """Draft/published snapshot boundary for the patent-status dataset."""

    __tablename__ = "patent_data_revisions"
    __table_args__ = (
        Index(
            "ix_patent_revision_workspace_dataset_status",
            "workspace_id",
            "dataset_key",
            "status",
        ),
        Index(
            "ix_patent_revision_workspace_dataset_no",
            "workspace_id",
            "dataset_key",
            "revision_no",
            unique=True,
        ),
        Index(
            "ux_patent_revision_active_draft",
            "workspace_id",
            "dataset_key",
            unique=True,
            postgresql_where=sa_text("status = 'draft'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default=PATENT_STATUS_DATASET_KEY,
        server_default=sa_text(f"'{PATENT_STATUS_DATASET_KEY}'"),
        index=True,
    )
    revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    base_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("patent_data_revisions.id"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    published_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    canceled_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    locked_by: Mapped["User | None"] = relationship("User", foreign_keys=[locked_by_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    published_by: Mapped["User | None"] = relationship("User", foreign_keys=[published_by_id])
    canceled_by: Mapped["User | None"] = relationship("User", foreign_keys=[canceled_by_id])


class PatentRecord(Base):
    """One patent row from the 특허현황관리 workbook (config-driven schema).

    Promoted columns are indexed for filtering and for the 출원번호 lookup the
    invoice pipeline relies on; the long tail of ~90 columns lives in
    ``field_values`` keyed by ``field_defs`` keys, with ``raw_fields`` holding
    the verbatim imported labels.
    """

    __tablename__ = "patent_records"
    __table_args__ = (
        Index("ix_patent_records_workspace_updated", "workspace_id", "updated_at"),
        Index(
            "ix_patent_records_workspace_disclosure_updated",
            "workspace_id",
            "disclosure_date",
            "updated_at",
        ),
        Index("ix_patent_records_workspace_app_no", "workspace_id", "application_no_norm"),
        Index("ix_patent_records_workspace_reg_no", "workspace_id", "registration_no"),
        Index("ix_patent_records_workspace_disclosure_year", "workspace_id", "disclosure_year"),
        Index("ix_patent_records_workspace_stage", "workspace_id", "current_stage"),
        Index("ix_patent_records_workspace_lifecycle", "workspace_id", "lifecycle_phase"),
        Index("ix_patent_records_workspace_revision", "workspace_id", "revision_id"),
        Index("ix_patent_records_workspace_stable", "workspace_id", "stable_record_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("patent_data_revisions.id"),
        nullable=True,
        index=True,
    )
    stable_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Promoted / queryable columns.
    application_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    application_no_norm: Mapped[str | None] = mapped_column(String(40), nullable=True)
    registration_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    invention_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inventors: Mapped[str | None] = mapped_column(Text, nullable=True)
    disclosure_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    disclosure_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    application_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    application_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patent_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lifecycle_phase: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Flexible payload.
    field_values: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    raw_fields: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)

    imported_source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    progress_events: Mapped[list["PatentProgressEvent"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
    )
    cost_lines: Mapped[list["PatentCostLine"]] = relationship(back_populates="record")


class PatentProgressEvent(Base):
    """One step of an accumulated ``날짜 단계-->`` progress log, structured.

    ``kind`` distinguishes the source column: 발명기술서검토현황 (H),
    초안명세서진행현황 (M), 심사청구진행현황 (AZ), 심사진행현황 (BB).
    The latest event's ``stage`` is mirrored onto ``PatentRecord.current_stage``.
    """

    __tablename__ = "patent_progress_events"
    __table_args__ = (
        Index(
            "ix_patent_progress_record_kind_seq",
            "record_id",
            "kind",
            "seq",
        ),
        Index("ix_patent_progress_workspace", "workspace_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    record_id: Mapped[str] = mapped_column(
        ForeignKey("patent_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    stage: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    record: Mapped[PatentRecord] = relationship(back_populates="progress_events")


class PatentCostRun(Base):
    """A single invoice-ingestion execution that produces the summary files."""

    __tablename__ = "patent_cost_runs"
    __table_args__ = (
        Index("ix_patent_cost_runs_workspace_period", "workspace_id", "fiscal_period"),
        Index("ix_patent_cost_runs_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    fiscal_period: Mapped[str | None] = mapped_column(String(10), nullable=True)  # e.g. 2026-01
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    source_filenames: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    warnings: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    industrial_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    overseas_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    industrial_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overseas_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    lines: Mapped[list["PatentCostLine"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class PatentCostLine(Base):
    """One parsed invoice line, classified into a summary section.

    ``section`` ∈ {국내출원, 심사청구, 의견제출, 재심사, 특허등록, 연차료, 해외}.
    ``record_id`` is filled when the 출원번호 matched a ``PatentRecord`` so the
    summary can borrow 발명자/명칭/출원일/등록정보 from the database.
    """

    __tablename__ = "patent_cost_lines"
    __table_args__ = (
        Index("ix_patent_cost_lines_run", "run_id", "section"),
        Index("ix_patent_cost_lines_workspace_record", "workspace_id", "record_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("patent_cost_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_id: Mapped[str | None] = mapped_column(
        ForeignKey("patent_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    region: Mapped[str] = mapped_column(String(20), nullable=False)  # 산업 | 해외
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(40), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(60), nullable=True)
    application_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registration_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inventors: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    registration_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    annuity_year: Mapped[str | None] = mapped_column(String(20), nullable=True)
    supply_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 공급가액
    vat: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 부가세
    gov_fee: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 관납료
    line_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 합계 (KRW)
    foreign_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    foreign_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    foreign_cost_krw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reconciled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa_text("false"),
    )
    cost_details: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    run: Mapped[PatentCostRun] = relationship(back_populates="lines")
    record: Mapped["PatentRecord | None"] = relationship(back_populates="cost_lines")


class PatentRecordHistory(Base):
    """Per-field audit trail for patent records (mirrors legacy_issues)."""

    __tablename__ = "patent_record_history"
    __table_args__ = (
        Index(
            "ix_patent_history_record",
            "workspace_id",
            "record_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    field_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    details: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    actor: Mapped["User | None"] = relationship("User")
