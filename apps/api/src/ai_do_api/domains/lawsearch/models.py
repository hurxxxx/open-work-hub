from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


def _uuid() -> str:
    return str(uuid.uuid4())


class LawPartGroup(Base):
    __tablename__ = "lawsearch_part_groups"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(80), nullable=False)
    icon: Mapped[str] = mapped_column(String(16), default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=99, server_default=text("99"), nullable=False
    )


class LawPart(Base):
    __tablename__ = "lawsearch_parts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    group_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_part_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name_ko: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(16), default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=99, server_default=text("99"), nullable=False
    )


class LawRegion(Base):
    __tablename__ = "lawsearch_regions"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(80), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    flag: Mapped[str] = mapped_column(String(16), default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=99, server_default=text("99"), nullable=False
    )


class LawType(Base):
    __tablename__ = "lawsearch_types"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(80), nullable=False)
    name_en: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    icon: Mapped[str] = mapped_column(String(16), default="", server_default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=99, server_default=text("99"), nullable=False
    )


class LawItem(Base):
    __tablename__ = "lawsearch_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_en: Mapped[str] = mapped_column(String(400), default="", server_default="", nullable=False)
    type_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_types.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    caution: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    effective_date: Mapped[str] = mapped_column(
        String(40), default="", server_default="", nullable=False
    )
    revision_date: Mapped[str] = mapped_column(
        String(40), default="", server_default="", nullable=False
    )
    source_url: Mapped[str] = mapped_column(
        String(1024), default="", server_default="", nullable=False
    )
    note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    parts: Mapped[list["LawItemPart"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    regions: Mapped[list["LawItemRegion"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    history: Mapped[list["LawItemHistory"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LawItemHistory.sort_order",
    )


class LawItemPart(Base):
    __tablename__ = "lawsearch_item_parts"
    __table_args__ = (UniqueConstraint("item_id", "part_id", name="uq_lawsearch_item_parts"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_parts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # 원본 JSON 의 part_ids 배열 입력 순서 보존용. UI 표시 순서가 시드 그대로 유지된다.
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    item: Mapped[LawItem] = relationship(back_populates="parts")


class LawItemRegion(Base):
    __tablename__ = "lawsearch_item_regions"
    __table_args__ = (UniqueConstraint("item_id", "region_id", name="uq_lawsearch_item_regions"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_regions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    item: Mapped[LawItem] = relationship(back_populates="regions")


class LawItemHistory(Base):
    __tablename__ = "lawsearch_item_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(200), default="", server_default="", nullable=False)
    date: Mapped[str] = mapped_column(String(40), default="", server_default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="", server_default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    item: Mapped[LawItem] = relationship(back_populates="history")


class LawCompetitor(Base):
    __tablename__ = "lawsearch_competitors"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name_ko: Mapped[str] = mapped_column(String(120), nullable=False)
    name_en: Mapped[str] = mapped_column(String(160), default="", server_default="", nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="", server_default="", nullable=False)
    flag: Mapped[str] = mapped_column(String(16), default="", server_default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=99, server_default=text("99"), nullable=False
    )


class LawCompetitorSpec(Base):
    __tablename__ = "lawsearch_competitor_specs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    competitor_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_competitors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_en: Mapped[str] = mapped_column(String(400), default="", server_default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="", server_default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    caution: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    effective_date: Mapped[str] = mapped_column(
        String(40), default="", server_default="", nullable=False
    )
    revision_date: Mapped[str] = mapped_column(
        String(40), default="", server_default="", nullable=False
    )
    source_url: Mapped[str] = mapped_column(
        String(1024), default="", server_default="", nullable=False
    )
    note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    parts: Mapped[list["LawCompetitorSpecPart"]] = relationship(
        back_populates="spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LawCompetitorSpecPart(Base):
    __tablename__ = "lawsearch_competitor_spec_parts"
    __table_args__ = (
        UniqueConstraint("spec_id", "part_id", name="uq_lawsearch_competitor_spec_parts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    spec_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_competitor_specs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    part_id: Mapped[str] = mapped_column(
        ForeignKey("lawsearch_parts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )

    spec: Mapped[LawCompetitorSpec] = relationship(back_populates="parts")
