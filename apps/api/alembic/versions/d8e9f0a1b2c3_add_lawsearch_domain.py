"""add_lawsearch_domain

Revision ID: d8e9f0a1b2c3
Revises: b1d2c3e4f5a6
Create Date: 2026-05-29 12:00:00.000000

자동차 공조 부품의 지역별 법규·규제·자동차 표준 검색 도메인.
초기 seed 데이터(JSON 7종)는 src/ai_do_api/domains/lawsearch/sample_data/ 에서 읽어 삽입.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "b1d2c3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "ai_do_api"
    / "domains"
    / "lawsearch"
    / "sample_data"
)


def _load_json(name: str) -> list[dict]:
    p = SEED_DIR / name
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def upgrade() -> None:
    # ─── Tables ─────────────────────────────────────────────────────
    op.create_table(
        "lawsearch_part_groups",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name_ko", sa.String(length=80), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="99"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lawsearch_parts",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("group_id", sa.String(length=40), nullable=False),
        sa.Column("name_ko", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="99"),
        sa.ForeignKeyConstraint(["group_id"], ["lawsearch_part_groups.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lawsearch_parts_group_id", "lawsearch_parts", ["group_id"])

    op.create_table(
        "lawsearch_regions",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("name_ko", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("flag", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="99"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lawsearch_types",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name_ko", sa.String(length=80), nullable=False),
        sa.Column("name_en", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="99"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lawsearch_items",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("name_en", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("type_id", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("caution", sa.Text(), nullable=False, server_default=""),
        sa.Column("effective_date", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("revision_date", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["type_id"], ["lawsearch_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lawsearch_items_type_id", "lawsearch_items", ["type_id"])

    op.create_table(
        "lawsearch_item_parts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("part_id", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["item_id"], ["lawsearch_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["part_id"], ["lawsearch_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "part_id", name="uq_lawsearch_item_parts"),
    )
    op.create_index("ix_lawsearch_item_parts_item_id", "lawsearch_item_parts", ["item_id"])
    op.create_index("ix_lawsearch_item_parts_part_id", "lawsearch_item_parts", ["part_id"])

    op.create_table(
        "lawsearch_item_regions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("region_id", sa.String(length=20), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["item_id"], ["lawsearch_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["region_id"], ["lawsearch_regions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("item_id", "region_id", name="uq_lawsearch_item_regions"),
    )
    op.create_index("ix_lawsearch_item_regions_item_id", "lawsearch_item_regions", ["item_id"])
    op.create_index("ix_lawsearch_item_regions_region_id", "lawsearch_item_regions", ["region_id"])

    op.create_table(
        "lawsearch_item_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("date", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["item_id"], ["lawsearch_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lawsearch_item_history_item_id", "lawsearch_item_history", ["item_id"])

    op.create_table(
        "lawsearch_competitors",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("name_ko", sa.String(length=120), nullable=False),
        sa.Column("name_en", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("flag", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="99"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "lawsearch_competitor_specs",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("competitor_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("name_en", sa.String(length=400), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("caution", sa.Text(), nullable=False, server_default=""),
        sa.Column("effective_date", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("revision_date", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["competitor_id"], ["lawsearch_competitors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lawsearch_competitor_specs_competitor_id",
        "lawsearch_competitor_specs",
        ["competitor_id"],
    )

    op.create_table(
        "lawsearch_competitor_spec_parts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("spec_id", sa.String(length=40), nullable=False),
        sa.Column("part_id", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["spec_id"], ["lawsearch_competitor_specs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["part_id"], ["lawsearch_parts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("spec_id", "part_id", name="uq_lawsearch_competitor_spec_parts"),
    )
    op.create_index(
        "ix_lawsearch_competitor_spec_parts_spec_id",
        "lawsearch_competitor_spec_parts",
        ["spec_id"],
    )
    op.create_index(
        "ix_lawsearch_competitor_spec_parts_part_id",
        "lawsearch_competitor_spec_parts",
        ["part_id"],
    )

    # ─── Seed data (from sample_data/*.json) ────────────────────────
    _seed()


def _parse_dt(s: str | None) -> str | None:
    """Pass through ISO-ish strings as-is; the SQLAlchemy DateTime column accepts datetime — we
    let sa convert via the connection's adapter. For seed we just pass datetime objects."""
    if not s:
        return None
    return s


def _seed() -> None:
    from datetime import datetime

    bind = op.get_bind()
    meta = sa.MetaData()
    t_groups = sa.Table("lawsearch_part_groups", meta, autoload_with=bind)
    t_parts = sa.Table("lawsearch_parts", meta, autoload_with=bind)
    t_regions = sa.Table("lawsearch_regions", meta, autoload_with=bind)
    t_types = sa.Table("lawsearch_types", meta, autoload_with=bind)
    t_items = sa.Table("lawsearch_items", meta, autoload_with=bind)
    t_item_parts = sa.Table("lawsearch_item_parts", meta, autoload_with=bind)
    t_item_regions = sa.Table("lawsearch_item_regions", meta, autoload_with=bind)
    t_history = sa.Table("lawsearch_item_history", meta, autoload_with=bind)
    t_competitors = sa.Table("lawsearch_competitors", meta, autoload_with=bind)
    t_specs = sa.Table("lawsearch_competitor_specs", meta, autoload_with=bind)
    t_spec_parts = sa.Table("lawsearch_competitor_spec_parts", meta, autoload_with=bind)

    now = datetime.utcnow()

    groups = _load_json("part_groups.json")
    if groups:
        bind.execute(
            t_groups.insert(),
            [
                {"id": g["id"], "name_ko": g.get("name_ko", ""), "icon": g.get("icon", ""), "sort_order": g.get("order", 99)}
                for g in groups
            ],
        )

    parts = _load_json("parts.json")
    if parts:
        bind.execute(
            t_parts.insert(),
            [
                {
                    "id": p["id"],
                    "group_id": p.get("group", ""),
                    "name_ko": p.get("name_ko", ""),
                    "name_en": p.get("name_en", "") or "",
                    "icon": p.get("icon", "") or "",
                    "sort_order": p.get("order", 99),
                }
                for p in parts
            ],
        )

    regions = _load_json("regions.json")
    if regions:
        bind.execute(
            t_regions.insert(),
            [
                {
                    "id": r["id"],
                    "name_ko": r.get("name_ko", ""),
                    "name_en": r.get("name_en", "") or "",
                    "flag": r.get("flag", "") or "",
                    "sort_order": r.get("order", 99),
                }
                for r in regions
            ],
        )

    types = _load_json("types.json")
    if types:
        bind.execute(
            t_types.insert(),
            [
                {
                    "id": t["id"],
                    "name_ko": t.get("name_ko", ""),
                    "name_en": t.get("name_en", "") or "",
                    "icon": t.get("icon", "") or "",
                    "description": t.get("desc", "") or "",
                    "sort_order": t.get("order", 99),
                }
                for t in types
            ],
        )

    items = _load_json("items.json")
    item_rows = []
    item_part_rows = []
    item_region_rows = []
    history_rows = []
    for it in items:
        created = _parse_iso(it.get("created_at")) or now
        updated = _parse_iso(it.get("updated_at")) or now
        item_rows.append(
            {
                "id": it["id"],
                "name": it.get("name", ""),
                "name_en": it.get("name_en", "") or "",
                "type_id": it.get("type", ""),
                "description": it.get("description", "") or "",
                "caution": it.get("caution", "") or "",
                "effective_date": it.get("effective_date", "") or "",
                "revision_date": it.get("revision_date", "") or "",
                "source_url": it.get("source_url", "") or "",
                "note": it.get("note", "") or "",
                "created_at": created,
                "updated_at": updated,
            }
        )
        for i, pid in enumerate(dict.fromkeys(it.get("part_ids", []) or [])):
            item_part_rows.append(
                {"id": str(uuid.uuid4()), "item_id": it["id"], "part_id": pid, "sort_order": i}
            )
        for i, rid in enumerate(dict.fromkeys(it.get("region_ids", []) or [])):
            item_region_rows.append(
                {"id": str(uuid.uuid4()), "item_id": it["id"], "region_id": rid, "sort_order": i}
            )
        for i, h in enumerate(it.get("history", []) or []):
            history_rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "item_id": it["id"],
                    "version": h.get("version", "") or "",
                    "date": h.get("date", "") or "",
                    "status": h.get("status", "") or "",
                    "summary": h.get("summary", "") or "",
                    "sort_order": i,
                }
            )
    if item_rows:
        bind.execute(t_items.insert(), item_rows)
    if item_part_rows:
        bind.execute(t_item_parts.insert(), item_part_rows)
    if item_region_rows:
        bind.execute(t_item_regions.insert(), item_region_rows)
    if history_rows:
        bind.execute(t_history.insert(), history_rows)

    competitors = _load_json("competitors.json")
    if competitors:
        bind.execute(
            t_competitors.insert(),
            [
                {
                    "id": c["id"],
                    "name_ko": c.get("name_ko", ""),
                    "name_en": c.get("name_en", "") or "",
                    "country": c.get("country", "") or "",
                    "flag": c.get("flag", "") or "",
                    "note": c.get("note", "") or "",
                    "sort_order": c.get("order", 99),
                }
                for c in competitors
            ],
        )

    specs = _load_json("competitor_specs.json")
    spec_rows = []
    spec_part_rows = []
    for s in specs:
        created = _parse_iso(s.get("created_at")) or now
        updated = _parse_iso(s.get("updated_at")) or now
        spec_rows.append(
            {
                "id": s["id"],
                "competitor_id": s.get("competitor_id", ""),
                "name": s.get("name", ""),
                "name_en": s.get("name_en", "") or "",
                "category": s.get("category", "") or "",
                "description": s.get("description", "") or "",
                "caution": s.get("caution", "") or "",
                "effective_date": s.get("effective_date", "") or "",
                "revision_date": s.get("revision_date", "") or "",
                "source_url": s.get("source_url", "") or "",
                "note": s.get("note", "") or "",
                "created_at": created,
                "updated_at": updated,
            }
        )
        for i, pid in enumerate(dict.fromkeys(s.get("part_ids", []) or [])):
            spec_part_rows.append(
                {"id": str(uuid.uuid4()), "spec_id": s["id"], "part_id": pid, "sort_order": i}
            )
    if spec_rows:
        bind.execute(t_specs.insert(), spec_rows)
    if spec_part_rows:
        bind.execute(t_spec_parts.insert(), spec_part_rows)


def _parse_iso(s):
    from datetime import datetime

    if not s or not isinstance(s, str):
        return None
    try:
        # accept "...Z" by replacing with "+00:00"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        # store naive UTC
        if dt.tzinfo is not None:
            from datetime import timezone

            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def downgrade() -> None:
    op.drop_table("lawsearch_competitor_spec_parts")
    op.drop_table("lawsearch_competitor_specs")
    op.drop_table("lawsearch_competitors")
    op.drop_table("lawsearch_item_history")
    op.drop_table("lawsearch_item_regions")
    op.drop_table("lawsearch_item_parts")
    op.drop_table("lawsearch_items")
    op.drop_table("lawsearch_types")
    op.drop_table("lawsearch_regions")
    op.drop_table("lawsearch_parts")
    op.drop_table("lawsearch_part_groups")
