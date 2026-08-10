from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.lawsearch import schemas as S
from open_alm_api.domains.lawsearch.models import (
    LawCompetitor,
    LawCompetitorSpec,
    LawItem,
    LawItemHistory,
    LawItemPart,
    LawItemRegion,
    LawPart,
    LawPartGroup,
    LawRegion,
    LawType,
)

_ALLOWED_SOURCE_URL_SCHEMES = {"http", "https"}


# ═══════════════════════════════════════════════════════════════════
# Card views — counts aggregations
# ═══════════════════════════════════════════════════════════════════


def list_parts(db: Session) -> S.PartsResponse:
    groups = db.execute(
        select(LawPartGroup).order_by(LawPartGroup.sort_order, LawPartGroup.id)
    ).scalars().all()
    parts = db.execute(
        select(LawPart).order_by(LawPart.sort_order, LawPart.id)
    ).scalars().all()

    counts_rows = db.execute(
        select(LawItemPart.part_id, func.count(LawItemPart.id)).group_by(LawItemPart.part_id)
    ).all()
    counts = {pid: int(c) for pid, c in counts_rows}

    parts_by_group: dict[str, list[S.PartSummary]] = {g.id: [] for g in groups}
    for p in parts:
        if p.group_id not in parts_by_group:
            continue
        parts_by_group[p.group_id].append(
            S.PartSummary(
                id=p.id,
                name_ko=p.name_ko,
                name_en=p.name_en,
                icon=p.icon,
                count=counts.get(p.id, 0),
            )
        )

    return S.PartsResponse(
        groups=[
            S.PartGroupOut(
                id=g.id, name_ko=g.name_ko, icon=g.icon, parts=parts_by_group[g.id]
            )
            for g in groups
        ]
    )


def list_regions(db: Session) -> S.RegionsResponse:
    regions = db.execute(
        select(LawRegion).order_by(LawRegion.sort_order, LawRegion.id)
    ).scalars().all()
    counts_rows = db.execute(
        select(LawItemRegion.region_id, func.count(LawItemRegion.id)).group_by(
            LawItemRegion.region_id
        )
    ).all()
    counts = {rid: int(c) for rid, c in counts_rows}

    return S.RegionsResponse(
        regions=[
            S.RegionOut(
                id=r.id,
                name_ko=r.name_ko,
                name_en=r.name_en,
                flag=r.flag,
                count=counts.get(r.id, 0),
            )
            for r in regions
        ]
    )


def list_types(db: Session) -> S.TypesResponse:
    types = db.execute(
        select(LawType).order_by(LawType.sort_order, LawType.id)
    ).scalars().all()
    counts_rows = db.execute(
        select(LawItem.type_id, func.count(LawItem.id)).group_by(LawItem.type_id)
    ).all()
    counts = {tid: int(c) for tid, c in counts_rows}

    out: list[S.TypeOut] = [
        S.TypeOut(
            id=t.id,
            name_ko=t.name_ko,
            name_en=t.name_en,
            icon=t.icon,
            desc=t.description,
            count=counts.get(t.id, 0),
        )
        for t in types
    ]

    competitor_count = int(db.execute(select(func.count(LawCompetitorSpec.id))).scalar() or 0)
    out.append(
        S.TypeOut(
            id="competitors",
            name_ko="경쟁사",
            name_en="Competitors",
            icon="",
            desc="공급사·OEM 협력사 자체 사양 (DENSO·Hanon·Valeo 등)",
            count=competitor_count,
            is_virtual=True,
        )
    )
    return S.TypesResponse(types=out)


# ═══════════════════════════════════════════════════════════════════
# Item resolution / sorting
# ═══════════════════════════════════════════════════════════════════


def _items_query():
    return (
        select(LawItem)
        .options(
            selectinload(LawItem.parts),
            selectinload(LawItem.regions),
            selectinload(LawItem.history),
        )
    )


def _resolve_items(db: Session, items: Iterable[LawItem]) -> list[S.LawItemOut]:
    items_list = list(items)
    part_ids = {p.part_id for it in items_list for p in it.parts}
    region_ids = {r.region_id for it in items_list for r in it.regions}
    type_ids = {it.type_id for it in items_list}

    parts_by_id = (
        {
            p.id: p
            for p in db.execute(select(LawPart).where(LawPart.id.in_(part_ids))).scalars()
        }
        if part_ids
        else {}
    )
    regions_by_id = (
        {
            r.id: r
            for r in db.execute(
                select(LawRegion).where(LawRegion.id.in_(region_ids))
            ).scalars()
        }
        if region_ids
        else {}
    )
    types_by_id = (
        {
            t.id: t
            for t in db.execute(select(LawType).where(LawType.id.in_(type_ids))).scalars()
        }
        if type_ids
        else {}
    )

    out: list[S.LawItemOut] = []
    for it in items_list:
        # 원본 Flask 앱은 JSON 시드의 part_ids / region_ids 배열 입력 순서를
        # 그대로 유지한다. 그 의미를 보존하기 위해 LawItemPart / LawItemRegion
        # 행을 sort_order(입력 시점에 기록된 인덱스) 로 정렬한다.
        sorted_parts = sorted(it.parts, key=lambda link: (link.sort_order, link.part_id))
        part_refs = [
            S.PartRef(id=p.id, name_ko=p.name_ko, icon=p.icon)
            for link in sorted_parts
            if (p := parts_by_id.get(link.part_id))
        ]
        sorted_regions = sorted(it.regions, key=lambda link: (link.sort_order, link.region_id))
        region_refs = [
            S.RegionRef(id=r.id, name_ko=r.name_ko, flag=r.flag)
            for link in sorted_regions
            if (r := regions_by_id.get(link.region_id))
        ]
        t = types_by_id.get(it.type_id)
        type_ref = S.TypeRef(id=t.id, name_ko=t.name_ko, icon=t.icon) if t else None
        out.append(
            S.LawItemOut(
                id=it.id,
                name=it.name,
                name_en=it.name_en,
                type=it.type_id,
                part_ids=[p.id for p in part_refs],
                region_ids=[r.id for r in region_refs],
                description=it.description,
                caution=it.caution,
                effective_date=it.effective_date,
                revision_date=it.revision_date,
                source_url=it.source_url,
                note=it.note,
                history=[
                    S.HistoryEntry(version=h.version, date=h.date, status=h.status, summary=h.summary)
                    for h in sorted(it.history, key=lambda x: x.sort_order)
                ],
                created_at=it.created_at,
                updated_at=it.updated_at,
                parts=part_refs,
                regions=region_refs,
                type_info=type_ref,
            )
        )
    return out


def _latest_sort_key(it: S.LawItemOut) -> str:
    return it.revision_date or it.effective_date or ""


def _sort_latest(items: list[S.LawItemOut]) -> list[S.LawItemOut]:
    return sorted(items, key=_latest_sort_key, reverse=True)


# ═══════════════════════════════════════════════════════════════════
# By-part / by-region / by-type / search
# ═══════════════════════════════════════════════════════════════════


def by_part(db: Session, part_id: str) -> S.ByPartResponse | None:
    part = db.get(LawPart, part_id)
    if not part:
        return None
    items = (
        db.execute(_items_query().join(LawItemPart).where(LawItemPart.part_id == part_id))
        .scalars()
        .unique()
        .all()
    )
    return S.ByPartResponse(
        part=S.PartRef(id=part.id, name_ko=part.name_ko, icon=part.icon),
        items=_sort_latest(_resolve_items(db, items)),
    )


def by_region(db: Session, region_id: str) -> S.ByRegionResponse | None:
    region = db.get(LawRegion, region_id)
    if not region:
        return None
    items = (
        db.execute(
            _items_query().join(LawItemRegion).where(LawItemRegion.region_id == region_id)
        )
        .scalars()
        .unique()
        .all()
    )
    return S.ByRegionResponse(
        region=S.RegionRef(id=region.id, name_ko=region.name_ko, flag=region.flag),
        items=_sort_latest(_resolve_items(db, items)),
    )


def by_type(db: Session, type_id: str) -> S.ByTypeResponse | None:
    type_obj = db.get(LawType, type_id)
    if not type_obj:
        return None
    items = (
        db.execute(_items_query().where(LawItem.type_id == type_id))
        .scalars()
        .unique()
        .all()
    )
    return S.ByTypeResponse(
        type=S.TypeRef(id=type_obj.id, name_ko=type_obj.name_ko, icon=type_obj.icon),
        items=_sort_latest(_resolve_items(db, items)),
    )


def search(db: Session, q: str) -> S.SearchResponse:
    # 원본 Flask 앱과 동일하게 q 를 lower-case 로 정규화해서 검색하고,
    # 응답의 q 도 정규화된 값을 그대로 돌려준다.
    q = (q or "").strip().lower()
    if not q:
        return S.SearchResponse(items=[], q="")
    pattern = f"%{q}%"
    items = (
        db.execute(
            _items_query().where(
                (func.lower(LawItem.name).like(pattern))
                | (func.lower(LawItem.name_en).like(pattern))
                | (func.lower(LawItem.description).like(pattern))
                | (func.lower(LawItem.caution).like(pattern))
                | (func.lower(LawItem.note).like(pattern))
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return S.SearchResponse(items=_sort_latest(_resolve_items(db, items)), q=q)


# ═══════════════════════════════════════════════════════════════════
# Single item — raw read (admin edit form)
# ═══════════════════════════════════════════════════════════════════


def get_item_raw(db: Session, item_id: str) -> S.LawItemRaw | None:
    item = (
        db.execute(_items_query().where(LawItem.id == item_id)).unique().scalar_one_or_none()
    )
    if not item:
        return None
    return S.LawItemRaw(
        id=item.id,
        name=item.name,
        name_en=item.name_en,
        type=item.type_id,
        part_ids=[p.part_id for p in item.parts],
        region_ids=[r.region_id for r in item.regions],
        description=item.description,
        caution=item.caution,
        effective_date=item.effective_date,
        revision_date=item.revision_date,
        source_url=item.source_url,
        note=item.note,
        history=[
            S.HistoryEntry(version=h.version, date=h.date, status=h.status, summary=h.summary)
            for h in sorted(item.history, key=lambda x: x.sort_order)
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# ═══════════════════════════════════════════════════════════════════
# CRUD (admin)
# ═══════════════════════════════════════════════════════════════════


def _next_item_id(db: Session) -> str:
    ids = db.execute(select(LawItem.id)).scalars().all()
    max_n = 0
    for rid in ids:
        m = re.match(r"^reg-(\d+)$", rid or "")
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return f"reg-{max_n + 1:04d}"


def validate_payload(db: Session, payload: S.LawItemWriteIn) -> list[str]:
    errors: list[str] = []
    if not payload.name.strip():
        errors.append("법규/규제명(name)은 필수입니다")
    source_url_error = _validate_source_url(payload.source_url)
    if source_url_error:
        errors.append(source_url_error)
    valid_types = {t for (t,) in db.execute(select(LawType.id)).all()}
    if payload.type not in valid_types:
        errors.append(f"type은 {sorted(valid_types)} 중 하나여야 합니다")
    if payload.part_ids:
        valid_parts = {p for (p,) in db.execute(select(LawPart.id)).all()}
        bad = [p for p in payload.part_ids if p not in valid_parts]
        if bad:
            errors.append(f"알 수 없는 part_ids: {bad}")
    if payload.region_ids:
        valid_regions = {r for (r,) in db.execute(select(LawRegion.id)).all()}
        bad = [r for r in payload.region_ids if r not in valid_regions]
        if bad:
            errors.append(f"알 수 없는 region_ids: {bad}")
    return errors


def _validate_source_url(source_url: str) -> str | None:
    value = (source_url or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme.lower() not in _ALLOWED_SOURCE_URL_SCHEMES or not parsed.netloc:
        return "source_url은 http 또는 https URL이어야 합니다"
    return None


def create_item(db: Session, payload: S.LawItemWriteIn) -> S.LawItemRaw:
    item = LawItem(
        id=_next_item_id(db),
        name=payload.name.strip(),
        name_en=payload.name_en.strip(),
        type_id=payload.type,
        description=payload.description,
        caution=payload.caution,
        effective_date=payload.effective_date,
        revision_date=payload.revision_date,
        source_url=payload.source_url.strip(),
        note=payload.note,
    )
    for i, pid in enumerate(dict.fromkeys(payload.part_ids)):
        item.parts.append(LawItemPart(part_id=pid, sort_order=i))
    for i, rid in enumerate(dict.fromkeys(payload.region_ids)):
        item.regions.append(LawItemRegion(region_id=rid, sort_order=i))
    for i, h in enumerate(payload.history):
        item.history.append(
            LawItemHistory(version=h.version, date=h.date, status=h.status, summary=h.summary, sort_order=i)
        )
    db.add(item)
    db.flush()
    raw = get_item_raw(db, item.id)
    assert raw is not None
    return raw


def update_item(db: Session, item_id: str, payload: S.LawItemWriteIn) -> S.LawItemRaw | None:
    item = (
        db.execute(_items_query().where(LawItem.id == item_id)).unique().scalar_one_or_none()
    )
    if not item:
        return None
    item.name = payload.name.strip()
    item.name_en = payload.name_en.strip()
    item.type_id = payload.type
    item.description = payload.description
    item.caution = payload.caution
    item.effective_date = payload.effective_date
    item.revision_date = payload.revision_date
    item.source_url = payload.source_url.strip()
    item.note = payload.note

    item.parts.clear()
    for i, pid in enumerate(dict.fromkeys(payload.part_ids)):
        item.parts.append(LawItemPart(part_id=pid, sort_order=i))
    item.regions.clear()
    for i, rid in enumerate(dict.fromkeys(payload.region_ids)):
        item.regions.append(LawItemRegion(region_id=rid, sort_order=i))
    item.history.clear()
    for i, h in enumerate(payload.history):
        item.history.append(
            LawItemHistory(version=h.version, date=h.date, status=h.status, summary=h.summary, sort_order=i)
        )
    db.flush()
    return get_item_raw(db, item.id)


def delete_item(db: Session, item_id: str) -> bool:
    item = db.get(LawItem, item_id)
    if not item:
        return False
    db.delete(item)
    db.flush()
    return True


# ═══════════════════════════════════════════════════════════════════
# Competitors
# ═══════════════════════════════════════════════════════════════════


def list_competitors(db: Session) -> S.CompetitorsResponse:
    competitors = db.execute(
        select(LawCompetitor).order_by(LawCompetitor.sort_order, LawCompetitor.id)
    ).scalars().all()
    counts_rows = db.execute(
        select(LawCompetitorSpec.competitor_id, func.count(LawCompetitorSpec.id)).group_by(
            LawCompetitorSpec.competitor_id
        )
    ).all()
    counts = {cid: int(c) for cid, c in counts_rows}
    return S.CompetitorsResponse(
        competitors=[
            S.CompetitorOut(
                id=c.id,
                name_ko=c.name_ko,
                name_en=c.name_en,
                country=c.country,
                flag=c.flag,
                note=c.note,
                count=counts.get(c.id, 0),
            )
            for c in competitors
        ]
    )


def competitor_specs(db: Session, company_id: str) -> S.CompetitorSpecsResponse | None:
    company = db.get(LawCompetitor, company_id)
    if not company:
        return None
    specs = (
        db.execute(
            select(LawCompetitorSpec)
            .options(selectinload(LawCompetitorSpec.parts))
            .where(LawCompetitorSpec.competitor_id == company_id)
        )
        .scalars()
        .all()
    )
    part_ids = {p.part_id for s in specs for p in s.parts}
    parts_by_id = (
        {
            p.id: p
            for p in db.execute(select(LawPart).where(LawPart.id.in_(part_ids))).scalars()
        }
        if part_ids
        else {}
    )

    items: list[S.CompetitorSpecOut] = []
    for s in specs:
        sorted_links = sorted(s.parts, key=lambda link: (link.sort_order, link.part_id))
        part_refs = [
            S.PartRef(id=p.id, name_ko=p.name_ko, icon=p.icon)
            for link in sorted_links
            if (p := parts_by_id.get(link.part_id))
        ]
        items.append(
            S.CompetitorSpecOut(
                id=s.id,
                competitor_id=s.competitor_id,
                name=s.name,
                name_en=s.name_en,
                category=s.category,
                part_ids=[p.id for p in part_refs],
                description=s.description,
                caution=s.caution,
                effective_date=s.effective_date,
                revision_date=s.revision_date,
                source_url=s.source_url,
                note=s.note,
                created_at=s.created_at,
                updated_at=s.updated_at,
                parts=part_refs,
            )
        )
    items.sort(key=lambda x: x.revision_date or x.effective_date or "", reverse=True)
    return S.CompetitorSpecsResponse(
        company=S.CompetitorOut(
            id=company.id,
            name_ko=company.name_ko,
            name_en=company.name_en,
            country=company.country,
            flag=company.flag,
            note=company.note,
        ),
        items=items,
    )
