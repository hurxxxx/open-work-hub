from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


def _uuid() -> str:
    return str(uuid.uuid4())


class DataVizPerfData(Base):
    __tablename__ = "dataviz_perf_data"
    __table_args__ = (
        CheckConstraint("category IN ('가변','전동')", name="ck_dataviz_perf_data_category"),
        Index(
            "ix_dataviz_perf_data_workspace_filter",
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "source_file",
        ),
        Index("ix_dataviz_perf_data_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    refrigerant: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    test_group: Mapped[str] = mapped_column(String(40), default="", nullable=False, index=True)
    comp_type: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    serial_no: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    test_date: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    car_model: Mapped[str] = mapped_column(String(80), default="", nullable=False, index=True)
    engine_spec: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    remarks: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source_file: Mapped[str] = mapped_column(String(512), default="", nullable=False, index=True)
    rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    pd: Mapped[float | None] = mapped_column(Float, nullable=True)
    td: Mapped[float | None] = mapped_column(Float, nullable=True)
    ps: Mapped[float | None] = mapped_column(Float, nullable=True)
    ts: Mapped[float | None] = mapped_column(Float, nullable=True)
    pc: Mapped[float | None] = mapped_column(Float, nullable=True)
    mass_flow: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_eff: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr: Mapped[float | None] = mapped_column(Float, nullable=True)
    cooling_cap_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    cooling_cap_f: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_kw: Mapped[float | None] = mapped_column(Float, nullable=True)
    cop_sc: Mapped[float | None] = mapped_column(Float, nullable=True)
    heat_balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    torque: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    workspace = relationship("Workspace")
    owner = relationship("User")


class DataVizPerfProcessedFile(Base):
    __tablename__ = "dataviz_perf_processed_files"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "filename",
            "category",
            "refrigerant",
            "capacity",
            name="uq_dataviz_perf_processed_file_scope",
        ),
        Index(
            "ix_dataviz_perf_processed_files_filter",
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    refrigerant: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    workspace = relationship("Workspace")


class DataVizCarModelRef(Base):
    __tablename__ = "dataviz_car_model_refs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "code", name="uq_dataviz_car_model_ref_workspace_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    workspace = relationship("Workspace")


class DataVizPerfTolerance(Base):
    __tablename__ = "dataviz_perf_tolerance"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "car_model",
            "test_group",
            "field_name",
            name="uq_dataviz_perf_tolerance_scope",
        ),
        Index(
            "ix_dataviz_perf_tolerance_lookup",
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "car_model",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    refrigerant: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    car_model: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    test_group: Mapped[str] = mapped_column(String(40), nullable=False)
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    ref_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    tolerance: Mapped[float | None] = mapped_column(Float, nullable=True)

    workspace = relationship("Workspace")


class DataVizPerfToleranceProfile(Base):
    __tablename__ = "dataviz_perf_tol_profiles"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "profile_name",
            "test_group",
            "field_name",
            name="uq_dataviz_perf_tol_profile_scope",
        ),
        Index(
            "ix_dataviz_perf_tol_profiles_lookup",
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "profile_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    refrigerant: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'BASE'"))
    test_group: Mapped[str] = mapped_column(String(40), nullable=False)
    field_name: Mapped[str] = mapped_column(String(60), nullable=False)
    # 기준값(ref_value) 기준, 부호(sign)는 '±' | '+' | '-' | '편측'.
    # tol_value: ±/+/- 일 때 공차폭 / '편측'일 때 상한(+) 편차.
    # tol_lower: '편측'일 때만 하한(-) 편차. 그 외에는 NULL.
    ref_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sign: Mapped[str] = mapped_column(String(8), default="±", server_default=text("'±'"), nullable=False)
    tol_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    tol_lower: Mapped[float | None] = mapped_column(Float, nullable=True)

    workspace = relationship("Workspace")


class DataVizPerfToleranceProfileCar(Base):
    __tablename__ = "dataviz_perf_tol_profile_cars"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "category",
            "refrigerant",
            "capacity",
            "profile_name",
            "car_model",
            name="uq_dataviz_perf_tol_profile_car_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    refrigerant: Mapped[str] = mapped_column(String(16), nullable=False)
    capacity: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(80), nullable=False)
    car_model: Mapped[str] = mapped_column(String(80), nullable=False)

    workspace = relationship("Workspace")
