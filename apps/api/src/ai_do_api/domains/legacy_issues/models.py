from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    func,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import User, utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class LegacyIssueRecord(Base):
    __tablename__ = "legacy_issue_records"
    __table_args__ = (
        Index(
            "ix_legacy_issue_records_workspace_dataset_revision",
            "workspace_id",
            "dataset_key",
            "revision_id",
        ),
        Index(
            "ix_legacy_issue_records_scope_revision_updated_created",
            "workspace_id",
            "dataset_key",
            "revision_id",
            "updated_at",
            "created_at",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_updated",
            "workspace_id",
            "dataset_key",
            "updated_at",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_stable",
            "workspace_id",
            "dataset_key",
            "stable_record_id",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_department",
            "workspace_id",
            "dataset_key",
            "department",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_module",
            "workspace_id",
            "dataset_key",
            "module_key",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_module_revision",
            "workspace_id",
            "dataset_key",
            "module_key",
            "revision_id",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_issue_no",
            "workspace_id",
            "dataset_key",
            "legacy_issue_number",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_vehicle",
            "workspace_id",
            "dataset_key",
            "vehicle_model",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_stage",
            "workspace_id",
            "dataset_key",
            "occurrence_stage",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_type",
            "workspace_id",
            "dataset_key",
            "issue_type",
        ),
        Index(
            "ix_legacy_issue_records_workspace_dataset_applied",
            "workspace_id",
            "dataset_key",
            "applied",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    module_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id"),
        nullable=True,
        index=True,
    )
    stable_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    field_values: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    raw_fields: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    introduced_revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    registrant: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_issue_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    major_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    middle_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_zone: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    oem_open: Mapped[str | None] = mapped_column(Text, nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    supplier: Mapped[str | None] = mapped_column(Text, nullable=True)
    part_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    symptom: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    countermeasure: Mapped[str | None] = mapped_column(Text, nullable=True)
    countermeasure_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    oem_disclosure_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_grade: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmation_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_legacy_issue: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_design_check_sheet: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_design_fmea: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_design_standard_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_quality_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflected_revision: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    attachments: Mapped[list["LegacyIssueAttachment"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
    )


Index(
    "ix_legacy_issue_records_field_values_gin",
    LegacyIssueRecord.field_values,
    postgresql_using="gin",
).ddl_if(dialect="postgresql")
Index(
    "ix_legacy_issue_records_search_text_fts",
    func.to_tsvector(sa_text("'simple'"), func.coalesce(LegacyIssueRecord.search_text, "")),
    postgresql_using="gin",
).ddl_if(dialect="postgresql")
Index(
    "ix_legacy_issue_records_search_text_trgm",
    func.lower(LegacyIssueRecord.search_text).label("search_text_lower"),
    postgresql_using="gin",
    postgresql_ops={"search_text_lower": "gin_trgm_ops"},
).ddl_if(dialect="postgresql")


class LegacyIssueModuleField(Base):
    __tablename__ = "legacy_issue_module_fields"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "module_key",
            "field_key",
            name="uq_legacy_issue_module_fields_workspace_module_key",
        ),
        CheckConstraint(
            "field_type IN ('text', 'longText', 'number', 'date', 'select', 'boolean', 'user', 'orgUnit')",
            name="ck_legacy_issue_module_fields_type",
        ),
        Index(
            "ix_legacy_issue_module_fields_workspace_module_active_order",
            "workspace_id",
            "module_key",
            "active",
            "sort_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    module_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label_ko: Mapped[str] = mapped_column(String(120), nullable=False)
    label_en: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    options: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    allow_multiple: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa_text("false"),
        nullable=False,
    )
    required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa_text("false"),
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=sa_text("true"),
        nullable=False,
        index=True,
    )
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


class LegacyIssueSystemFieldSetting(Base):
    __tablename__ = "legacy_issue_system_field_settings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "field_key",
            name="uq_legacy_issue_system_field_settings_workspace_field",
        ),
        CheckConstraint(
            "field_type IN ('text', 'longText', 'number', 'date', 'select', 'boolean', 'user', 'orgUnit')",
            name="ck_legacy_issue_system_field_settings_type",
        ),
        Index(
            "ix_legacy_issue_system_field_settings_workspace_dataset",
            "workspace_id",
            "dataset_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label_ko: Mapped[str] = mapped_column(String(120), nullable=False)
    label_en: Mapped[str] = mapped_column(String(120), nullable=False)
    field_type: Mapped[str] = mapped_column(String(24), default="text", nullable=False)
    options: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    allow_multiple: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa_text("false"),
        nullable=False,
    )
    required: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa_text("false"),
        nullable=False,
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class LegacyIssueModuleAccessRule(Base):
    __tablename__ = "legacy_issue_module_access_rules"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "module_key",
            "subject_type",
            "subject_id",
            name="uq_legacy_issue_module_access_subject",
        ),
        CheckConstraint(
            "subject_type IN ('user', 'org_unit', 'team')",
            name="ck_legacy_issue_module_access_subject_type",
        ),
        CheckConstraint(
            "role IN ('viewer', 'editor', 'manager')",
            name="ck_legacy_issue_module_access_role",
        ),
        Index(
            "ix_legacy_issue_module_access_workspace_module_active",
            "workspace_id",
            "module_key",
            "active",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    module_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=sa_text("true"),
        nullable=False,
        index=True,
    )
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


class LegacyIssueColumnOrder(Base):
    __tablename__ = "legacy_issue_column_orders"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "view_key",
            name="uq_legacy_issue_column_orders_workspace_view",
        ),
        Index(
            "ix_legacy_issue_column_orders_workspace_view",
            "workspace_id",
            "view_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    view_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    column_order: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    hidden_column_keys: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class LegacyIssueGridPreference(Base):
    __tablename__ = "legacy_issue_grid_preferences"
    __table_args__ = (
        CheckConstraint(
            "grid_kind IN ('dataset', 'vehicle-module-checklist')",
            name="ck_legacy_issue_grid_preferences_grid_kind",
        ),
        CheckConstraint(
            "frozen_column_count >= 0 AND frozen_column_count <= 200",
            name="ck_legacy_issue_grid_preferences_frozen_column_count",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_legacy_issue_grid_preferences_revision",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    grid_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    grid_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    column_order: Mapped[list[str]] = mapped_column(JSONB_COMPAT, nullable=False)
    hidden_column_keys: Mapped[list[str]] = mapped_column(
        JSONB_COMPAT,
        nullable=False,
    )
    frozen_column_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=sa_text("1"),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=sa_text("false"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class LegacyIssueVehicleModel(Base):
    __tablename__ = "legacy_issue_vehicle_models"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "vehicle_code_normalized",
            name="uq_legacy_issue_vehicle_models_workspace_code",
        ),
        Index(
            "ix_legacy_issue_vehicle_models_workspace_active_code",
            "workspace_id",
            "active",
            "vehicle_code_normalized",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    vehicle_code: Mapped[str] = mapped_column(String(80), nullable=False)
    vehicle_code_normalized: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    vehicle_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=sa_text("true"),
        nullable=False,
        index=True,
    )
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

    checklist_revisions: Mapped[list["LegacyIssueVehicleChecklistRevision"]] = relationship(
        back_populates="vehicle_model",
        cascade="all, delete-orphan",
    )
    module_checklists: Mapped[list["LegacyIssueVehicleModuleChecklist"]] = relationship(
        back_populates="vehicle_model",
        cascade="all, delete-orphan",
    )
    stages: Mapped[list["LegacyIssueVehicleStage"]] = relationship(
        back_populates="vehicle_model",
        cascade="all, delete-orphan",
        order_by="LegacyIssueVehicleStage.sequence_no",
    )


class LegacyIssueVehicleStage(Base):
    __tablename__ = "legacy_issue_vehicle_stages"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "name_normalized",
            name="uq_li_vehicle_stages_vehicle_name",
        ),
        UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "sequence_no",
            name="uq_li_vehicle_stages_vehicle_sequence",
        ),
        Index(
            "ix_li_vehicle_stages_workspace_vehicle_sequence",
            "workspace_id",
            "vehicle_model_id",
            "sequence_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    vehicle_model_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_stage_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_vehicle_stages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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

    vehicle_model: Mapped[LegacyIssueVehicleModel] = relationship(back_populates="stages")
    previous_stage: Mapped["LegacyIssueVehicleStage | None"] = relationship(
        remote_side=[id],
        foreign_keys=[previous_stage_id],
    )
    module_checklists: Mapped[list["LegacyIssueVehicleModuleChecklist"]] = relationship(
        back_populates="vehicle_stage",
    )


class LegacyIssueVehicleChecklistRevision(Base):
    __tablename__ = "legacy_issue_vehicle_checklist_revisions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "revision_no",
            name="uq_legacy_issue_vehicle_checklist_revisions_vehicle_no",
        ),
        UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "source_master_revision_id",
            name="uq_legacy_issue_vehicle_checklist_revisions_vehicle_master",
        ),
        CheckConstraint(
            "status IN ('draft', 'completed')",
            name="ck_legacy_issue_vehicle_checklist_revisions_status",
        ),
        Index(
            "ix_legacy_issue_vehicle_checklist_revisions_workspace_vehicle",
            "workspace_id",
            "vehicle_model_id",
            "revision_no",
        ),
        Index(
            "ix_legacy_issue_vehicle_checklist_revisions_source_revision",
            "workspace_id",
            "source_master_revision_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    vehicle_model_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="draft",
        server_default=sa_text("'draft'"),
        nullable=False,
        index=True,
    )
    source_dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_master_revision_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id"),
        nullable=False,
        index=True,
    )
    source_master_revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    definition_snapshot: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    row_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=sa_text("0"),
        nullable=False,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    completed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    vehicle_model: Mapped[LegacyIssueVehicleModel] = relationship(
        back_populates="checklist_revisions"
    )
    records: Mapped[list["LegacyIssueVehicleChecklistRecord"]] = relationship(
        back_populates="checklist_revision",
        cascade="all, delete-orphan",
    )


class LegacyIssueVehicleChecklistRecord(Base):
    __tablename__ = "legacy_issue_vehicle_checklist_records"
    __table_args__ = (
        UniqueConstraint(
            "checklist_revision_id",
            "source_record_id",
            name="uq_legacy_issue_vehicle_checklist_records_source",
        ),
        Index(
            "ix_legacy_issue_vehicle_checklist_records_workspace_revision",
            "workspace_id",
            "checklist_revision_id",
            "sort_order",
        ),
        Index(
            "ix_legacy_issue_vehicle_checklist_records_revision_module",
            "checklist_revision_id",
            "source_module_key",
        ),
        Index(
            "ix_legacy_issue_vehicle_checklist_records_source_stable",
            "workspace_id",
            "source_stable_record_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    checklist_revision_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_checklist_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_stable_record_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    source_module_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    field_values: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    checklist_revision: Mapped[LegacyIssueVehicleChecklistRevision] = relationship(
        back_populates="records"
    )


class LegacyIssueVehicleModuleChecklist(Base):
    """A vehicle checklist bound to one module and one published master revision.

    The checklist intentionally has no revision number of its own. Its externally
    visible version is the source module master revision.
    """

    __tablename__ = "legacy_issue_vehicle_module_checklists"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "vehicle_stage_id",
            "module_key",
            "source_master_revision_id",
            name="uq_li_vehicle_module_checklists_scope_master",
        ),
        CheckConstraint(
            "status IN ('draft', 'completed')",
            name="ck_li_vehicle_module_checklists_status",
        ),
        Index(
            "ix_li_vehicle_module_checklists_workspace_vehicle_module",
            "workspace_id",
            "vehicle_model_id",
            "module_key",
        ),
        Index(
            "ix_li_vehicle_module_checklists_source_revision",
            "workspace_id",
            "source_master_revision_id",
        ),
        Index(
            "ix_li_vehicle_module_checklists_seeded_from",
            "seeded_from_checklist_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    vehicle_model_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vehicle_stage_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_stages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    module_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(24),
        default="draft",
        server_default=sa_text("'draft'"),
        nullable=False,
        index=True,
    )
    source_dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_master_revision_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id"),
        nullable=False,
        index=True,
    )
    source_master_revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    definition_snapshot: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    grid_layout: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    row_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=sa_text("0"),
        nullable=False,
    )
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    completed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    seeded_from_checklist_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_vehicle_module_checklists.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    vehicle_model: Mapped[LegacyIssueVehicleModel] = relationship(
        back_populates="module_checklists"
    )
    vehicle_stage: Mapped[LegacyIssueVehicleStage] = relationship(
        back_populates="module_checklists"
    )
    seeded_from_checklist: Mapped["LegacyIssueVehicleModuleChecklist | None"] = relationship(
        remote_side=[id],
        foreign_keys=[seeded_from_checklist_id],
    )
    records: Mapped[list["LegacyIssueVehicleModuleChecklistRecord"]] = relationship(
        back_populates="checklist",
        cascade="all, delete-orphan",
    )


class LegacyIssueVehicleModuleChecklistRecord(Base):
    __tablename__ = "legacy_issue_vehicle_module_checklist_records"
    __table_args__ = (
        UniqueConstraint(
            "checklist_id",
            "source_record_id",
            name="uq_li_vehicle_module_checklist_records_source",
        ),
        Index(
            "ix_li_vehicle_module_checklist_records_workspace_checklist",
            "workspace_id",
            "checklist_id",
            "sort_order",
        ),
        Index(
            "ix_li_vehicle_module_checklist_records_source_stable",
            "workspace_id",
            "source_stable_record_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    checklist_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_module_checklists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_record_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_stable_record_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    field_values: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    checklist: Mapped[LegacyIssueVehicleModuleChecklist] = relationship(back_populates="records")
    attachments: Mapped[list["LegacyIssueVehicleModuleChecklistAttachment"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
    )


class LegacyIssueVehicleModuleChecklistAttachment(Base):
    __tablename__ = "legacy_issue_vehicle_module_checklist_attachments"
    __table_args__ = (
        CheckConstraint(
            "size_bytes > 0",
            name="ck_li_vehicle_module_checklist_attachments_size",
        ),
        Index(
            "ix_li_vehicle_module_checklist_attachments_record_created",
            "record_id",
            "created_at",
        ),
        Index(
            "ix_li_vehicle_module_checklist_attachments_scope_created",
            "workspace_id",
            "checklist_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    checklist_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_module_checklists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_vehicle_module_checklist_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160),
        default="application/octet-stream",
        server_default=sa_text("'application/octet-stream'"),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    record: Mapped[LegacyIssueVehicleModuleChecklistRecord] = relationship(
        back_populates="attachments"
    )


class LegacyIssueVehicleModuleChecklistAttachmentCleanup(Base):
    """Durable outbox row for attachment objects removed after a DB commit."""

    __tablename__ = "legacy_issue_vehicle_module_checklist_attachment_cleanups"
    __table_args__ = (
        UniqueConstraint(
            "storage_key",
            name="uq_li_vehicle_module_checklist_attachment_cleanups_storage_key",
        ),
        Index(
            "ix_li_vehicle_module_checklist_attachment_cleanups_pending",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=sa_text("0"),
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class LegacyIssueExcelExportJob(Base):
    """Durable, requester-owned Excel export job and result pointer."""

    __tablename__ = "legacy_issue_excel_export_jobs"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('dataset','vehicle_module_checklist')",
            name="ck_legacy_issue_excel_export_jobs_source_kind",
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','expired')",
            name="ck_legacy_issue_excel_export_jobs_status",
        ),
        CheckConstraint(
            "record_count >= 0 AND attachment_count >= 0 "
            "AND attachment_bytes >= 0 AND processed_attachment_count >= 0 "
            "AND processed_attachment_bytes >= 0",
            name="ck_legacy_issue_excel_export_jobs_nonnegative_counts",
        ),
        Index(
            "ix_legacy_issue_excel_export_jobs_requester_created",
            "workspace_id",
            "requested_by_id",
            "created_at",
        ),
        Index(
            "ix_legacy_issue_excel_export_jobs_status_retry",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_legacy_issue_excel_export_jobs_expiry",
            "status",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    dataset_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    module_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    checklist_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_vehicle_module_checklists.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_params: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default="queued",
        server_default=sa_text("'queued'"),
        nullable=False,
        index=True,
    )
    record_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    attachment_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    attachment_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=sa_text("0"), nullable=False
    )
    processed_attachment_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    processed_attachment_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=sa_text("0"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    result_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class LegacyIssueAiChunk(Base):
    __tablename__ = "legacy_issue_ai_chunks"
    __table_args__ = (
        UniqueConstraint("record_id", "chunk_key", name="uq_legacy_issue_ai_chunks_record_chunk"),
        Index(
            "ix_legacy_issue_ai_chunks_workspace_dataset_revision",
            "workspace_id",
            "dataset_key",
            "revision_id",
        ),
        Index(
            "ix_legacy_issue_ai_chunks_pending_embedding_scope_updated",
            "workspace_id",
            "dataset_key",
            "revision_id",
            "updated_at",
            "created_at",
            postgresql_where=sa_text("embedding_vector IS NULL OR embedding_status <> 'embedded'"),
        ),
        Index("ix_legacy_issue_ai_chunks_record", "record_id", "chunk_kind"),
        Index("ix_legacy_issue_ai_chunks_attachment", "attachment_id", "chunk_kind"),
        Index(
            "ix_legacy_issue_ai_chunks_workspace_dataset_stable",
            "workspace_id",
            "dataset_key",
            "stable_record_id",
        ),
        Index("ix_legacy_issue_ai_chunks_embedding_status", "embedding_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    record_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stable_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attachment_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_attachments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    attachment_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    attachment_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attachment_artifact_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_key: Mapped[str] = mapped_column(String(160), nullable=False)
    chunk_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    field_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    field_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_terms: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    embedding_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        String(32),
        default="not_indexed",
        server_default=sa_text("'not_indexed'"),
        nullable=False,
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_metadata: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


Index(
    "ix_legacy_issue_ai_chunks_search_text_fts",
    func.to_tsvector(sa_text("'simple'"), func.coalesce(LegacyIssueAiChunk.search_text, "")),
    postgresql_using="gin",
).ddl_if(dialect="postgresql")
Index(
    "ix_legacy_issue_ai_chunks_search_text_trgm",
    func.lower(LegacyIssueAiChunk.search_text).label("search_text_lower"),
    postgresql_using="gin",
    postgresql_ops={"search_text_lower": "gin_trgm_ops"},
).ddl_if(dialect="postgresql")
Index(
    "ix_legacy_issue_ai_chunks_search_terms_gin",
    LegacyIssueAiChunk.search_terms,
    postgresql_using="gin",
).ddl_if(dialect="postgresql")
Index(
    "ix_legacy_issue_ai_chunks_embedding_hnsw",
    LegacyIssueAiChunk.embedding_vector.op("::")(sa_text("vector(1024)")).label(
        "embedding_vector_cosine"
    ),
    postgresql_using="hnsw",
    postgresql_ops={"embedding_vector_cosine": "vector_cosine_ops"},
    postgresql_where=sa_text("embedding_status = 'embedded' AND embedding_vector IS NOT NULL"),
).ddl_if(dialect="postgresql")


class LegacyIssueAssistantRun(Base):
    __tablename__ = "legacy_issue_assistant_runs"
    __table_args__ = (
        Index(
            "ix_legacy_issue_assistant_runs_workspace_created",
            "workspace_id",
            "created_at",
        ),
        Index(
            "ix_legacy_issue_assistant_runs_requested_by_created",
            "requested_by_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_plan: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    analysis_result: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    evidence: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    search_profile: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    gateway_decisions: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    requested_by: Mapped["User | None"] = relationship("User")


class LegacyIssueAttachment(Base):
    __tablename__ = "legacy_issue_attachments"
    __table_args__ = (
        Index("ix_legacy_issue_attachments_record", "record_id", "created_at"),
        Index("ix_legacy_issue_attachments_workspace", "workspace_id", "dataset_key", "created_at"),
        Index("ix_legacy_issue_attachments_index_status", "workspace_id", "index_status"),
        Index(
            "ix_legacy_issue_attachments_summary_status",
            "workspace_id",
            "ai_summary_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id"),
        nullable=True,
        index=True,
    )
    stable_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    record_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160),
        default="application/octet-stream",
        server_default=sa_text("'application/octet-stream'"),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_text("false"), nullable=False
    )
    index_status: Mapped[str] = mapped_column(
        String(32),
        default="not_indexed",
        server_default=sa_text("'not_indexed'"),
        nullable=False,
    )
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    index_version: Mapped[str] = mapped_column(
        String(80),
        default="legacy_issue_attachment_index.v1",
        server_default=sa_text("'legacy_issue_attachment_index.v1'"),
        nullable=False,
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    artifact_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_status: Mapped[str] = mapped_column(
        String(32),
        default="not_summarized",
        server_default=sa_text("'not_summarized'"),
        nullable=False,
    )
    ai_summary_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_summary_version: Mapped[str] = mapped_column(
        String(80),
        default="legacy_issue_attachment_summary.v1",
        server_default=sa_text("'legacy_issue_attachment_summary.v1'"),
        nullable=False,
    )
    ai_summarized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    record: Mapped[LegacyIssueRecord] = relationship(back_populates="attachments")


class LegacyIssueAttachmentIndexJob(Base):
    __tablename__ = "legacy_issue_attachment_index_jobs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('upsert','delete')",
            name="ck_legacy_issue_attachment_index_jobs_operation",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_legacy_issue_attachment_index_jobs_status",
        ),
        Index(
            "ix_legacy_issue_attachment_index_jobs_workspace_status_retry",
            "workspace_id",
            "status",
            "next_retry_at",
        ),
        Index(
            "ix_legacy_issue_attachment_index_jobs_attachment_status",
            "attachment_id",
            "status",
        ),
        Index(
            "uq_legacy_issue_attachment_index_jobs_pending_attachment",
            "workspace_id",
            "attachment_id",
            unique=True,
            postgresql_where=sa_text("status = 'pending'"),
            sqlite_where=sa_text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attachment_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_attachments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(
        String(16),
        default="upsert",
        server_default=sa_text("'upsert'"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(
        String(40),
        default="upload",
        server_default=sa_text("'upload'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default=sa_text("'pending'"),
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa_text("0"), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_context: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class LegacyIssueAttachmentArtifact(Base):
    __tablename__ = "legacy_issue_attachment_artifacts"
    __table_args__ = (
        Index(
            "ix_legacy_issue_attachment_artifacts_attachment",
            "attachment_id",
            "artifact_kind",
        ),
        Index(
            "ix_legacy_issue_attachment_artifacts_workspace_dataset",
            "workspace_id",
            "dataset_key",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    record_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stable_record_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    attachment_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_attachments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_attachment_index_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB_COMPAT,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class LegacyIssueRecordHistory(Base):
    __tablename__ = "legacy_issue_record_history"
    __table_args__ = (
        Index(
            "ix_legacy_issue_history_record",
            "workspace_id",
            "record_kind",
            "record_id",
            "created_at",
        ),
        Index(
            "ix_legacy_issue_history_dataset_record",
            "workspace_id",
            "dataset_key",
            "record_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    dataset_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
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


class LegacyIssueDataRevision(Base):
    __tablename__ = "legacy_issue_data_revisions"
    __table_args__ = (
        Index(
            "ix_legacy_issue_revision_workspace_dataset_status",
            "workspace_id",
            "dataset_key",
            "status",
        ),
        Index(
            "ix_legacy_issue_revision_workspace_dataset_no",
            "workspace_id",
            "dataset_key",
            "revision_no",
            unique=True,
        ),
        Index(
            "ux_legacy_issue_revision_active_draft",
            "workspace_id",
            "dataset_key",
            unique=True,
            postgresql_where=sa_text("status = 'draft'"),
            sqlite_where=sa_text("status = 'draft'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    base_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id"),
        nullable=True,
        index=True,
    )
    grid_layout: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
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
    reviewer_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    approver_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    review_requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    approval_requested_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    reviewed_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    approved_by_id: Mapped[str | None] = mapped_column(
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
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    locked_by: Mapped["User | None"] = relationship("User", foreign_keys=[locked_by_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    published_by: Mapped["User | None"] = relationship("User", foreign_keys=[published_by_id])
    canceled_by: Mapped["User | None"] = relationship("User", foreign_keys=[canceled_by_id])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewer_id])
    approver: Mapped["User | None"] = relationship("User", foreign_keys=[approver_id])
    review_requested_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[review_requested_by_id]
    )
    approval_requested_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[approval_requested_by_id]
    )
    reviewed_by: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])


class LegacyIssueRevisionOverviewHistory(Base):
    __tablename__ = "legacy_issue_revision_overview_history"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "source_filename",
            "source_sheet",
            "source_row",
            name="uq_legacy_issue_revision_overview_history_source_row",
        ),
        Index(
            "ix_legacy_issue_revision_overview_history_dataset_order",
            "workspace_id",
            "dataset_key",
            "sort_order",
        ),
        Index(
            "ux_legacy_issue_revision_overview_history_active_number",
            "workspace_id",
            "dataset_key",
            "revision_no",
            unique=True,
            postgresql_where=sa_text("deleted_at IS NULL AND revision_no IS NOT NULL"),
            sqlite_where=sa_text("deleted_at IS NULL AND revision_no IS NOT NULL"),
        ),
        Index(
            "ux_legacy_issue_revision_overview_history_active_link",
            "workspace_id",
            "dataset_key",
            "linked_revision_id",
            unique=True,
            postgresql_where=sa_text("deleted_at IS NULL AND linked_revision_id IS NOT NULL"),
            sqlite_where=sa_text("deleted_at IS NULL AND linked_revision_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    linked_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin: Mapped[str] = mapped_column(String(20), default="imported", nullable=False)
    revision_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    revised_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    vehicle_models: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approver_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approver_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    author_user: Mapped["User | None"] = relationship("User", foreign_keys=[author_user_id])
    reviewer_user: Mapped["User | None"] = relationship("User", foreign_keys=[reviewer_user_id])
    approver_user: Mapped["User | None"] = relationship("User", foreign_keys=[approver_user_id])
    linked_revision: Mapped["LegacyIssueDataRevision | None"] = relationship(
        "LegacyIssueDataRevision", foreign_keys=[linked_revision_id]
    )
    deleted_by: Mapped["User | None"] = relationship("User", foreign_keys=[deleted_by_id])


class LegacyIssueRevisionMeetingAttachment(Base):
    __tablename__ = "legacy_issue_revision_meeting_attachments"
    __table_args__ = (
        CheckConstraint(
            "size_bytes > 0",
            name="ck_legacy_issue_revision_meeting_attachments_size",
        ),
        UniqueConstraint(
            "storage_key",
            name="uq_legacy_issue_revision_meeting_attachments_storage_key",
        ),
        UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "overview_history_id",
            "uploaded_by_id",
            "client_request_id",
            name="uq_li_revision_meeting_attachment_request",
        ),
        CheckConstraint(
            "length(client_request_id) BETWEEN 1 AND 64",
            name="ck_li_revision_meeting_attachment_request_length",
        ),
        Index(
            "ix_li_revision_meeting_attachments_scope_history_created",
            "workspace_id",
            "dataset_key",
            "overview_history_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False)
    overview_history_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_revision_overview_history.id", ondelete="RESTRICT"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160),
        default="application/octet-stream",
        server_default=sa_text("'application/octet-stream'"),
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    uploaded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    client_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    overview_history: Mapped["LegacyIssueRevisionOverviewHistory"] = relationship(
        "LegacyIssueRevisionOverviewHistory"
    )
    uploaded_by: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])


class LegacyIssueRevisionMeetingAttachmentCleanup(Base):
    """Durable outbox row for meeting attachment objects deleted after commit."""

    __tablename__ = "legacy_issue_revision_meeting_attachment_cleanups"
    __table_args__ = (
        UniqueConstraint(
            "storage_key",
            name="uq_li_revision_meeting_attachment_cleanups_storage_key",
        ),
        Index(
            "ix_li_revision_meeting_attachment_cleanups_pending",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=sa_text("0"),
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class LegacyIssueDataRevisionEvent(Base):
    __tablename__ = "legacy_issue_data_revision_events"
    __table_args__ = (
        Index("ix_legacy_issue_revision_event_revision", "revision_id", "created_at"),
        Index(
            "ix_legacy_issue_revision_event_workspace_dataset",
            "workspace_id",
            "dataset_key",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("legacy_issue_data_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    revision: Mapped[LegacyIssueDataRevision] = relationship("LegacyIssueDataRevision")
    actor: Mapped["User | None"] = relationship("User")
