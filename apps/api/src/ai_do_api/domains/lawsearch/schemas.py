from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─── Master data DTOs ─────────────────────────────────────────────────


class PartSummary(BaseModel):
    id: str
    name_ko: str
    name_en: str = ""
    icon: str = ""
    count: int = 0


class PartGroupOut(BaseModel):
    id: str
    name_ko: str
    icon: str = ""
    parts: list[PartSummary]


class PartsResponse(BaseModel):
    groups: list[PartGroupOut]


class RegionOut(BaseModel):
    id: str
    name_ko: str
    name_en: str = ""
    flag: str = ""
    count: int = 0


class RegionsResponse(BaseModel):
    regions: list[RegionOut]


class TypeOut(BaseModel):
    id: str
    name_ko: str
    name_en: str = ""
    icon: str = ""
    desc: str = ""
    count: int = 0
    is_virtual: bool = False


class TypesResponse(BaseModel):
    types: list[TypeOut]


# ─── Item DTOs ────────────────────────────────────────────────────────


class HistoryEntry(BaseModel):
    version: str = ""
    date: str = ""
    status: str = ""
    summary: str = ""


class PartRef(BaseModel):
    id: str
    name_ko: str
    icon: str = ""


class RegionRef(BaseModel):
    id: str
    name_ko: str
    flag: str = ""


class TypeRef(BaseModel):
    id: str
    name_ko: str
    icon: str = ""


class LawItemOut(BaseModel):
    """Item with parts/regions/type resolved by name (for table rendering)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    name_en: str = ""
    type: str
    part_ids: list[str] = []
    region_ids: list[str] = []
    description: str = ""
    caution: str = ""
    effective_date: str = ""
    revision_date: str = ""
    source_url: str = ""
    note: str = ""
    history: list[HistoryEntry] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # resolved (server-side)
    parts: list[PartRef] = []
    regions: list[RegionRef] = []
    type_info: TypeRef | None = None


class LawItemRaw(BaseModel):
    """Raw item record for admin edit form (no resolved names)."""

    id: str
    name: str
    name_en: str = ""
    type: str
    part_ids: list[str] = []
    region_ids: list[str] = []
    description: str = ""
    caution: str = ""
    effective_date: str = ""
    revision_date: str = ""
    source_url: str = ""
    note: str = ""
    history: list[HistoryEntry] = []
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LawItemWriteIn(BaseModel):
    """Payload for create/update of a LawItem from admin UI."""

    name: str = Field(..., min_length=1, max_length=300)
    name_en: str = ""
    type: str
    part_ids: list[str] = []
    region_ids: list[str] = []
    description: str = ""
    caution: str = ""
    effective_date: str = ""
    revision_date: str = ""
    source_url: str = ""
    note: str = ""
    history: list[HistoryEntry] = []


class ByPartResponse(BaseModel):
    part: PartRef
    items: list[LawItemOut]


class ByRegionResponse(BaseModel):
    region: RegionRef
    items: list[LawItemOut]


class ByTypeResponse(BaseModel):
    type: TypeRef
    items: list[LawItemOut]


class SearchResponse(BaseModel):
    items: list[LawItemOut]
    q: str = ""


# ─── Competitor DTOs ──────────────────────────────────────────────────


class CompetitorOut(BaseModel):
    id: str
    name_ko: str
    name_en: str = ""
    country: str = ""
    flag: str = ""
    note: str = ""
    count: int = 0


class CompetitorsResponse(BaseModel):
    competitors: list[CompetitorOut]


class CompetitorSpecOut(BaseModel):
    id: str
    competitor_id: str
    name: str
    name_en: str = ""
    category: str = ""
    part_ids: list[str] = []
    description: str = ""
    caution: str = ""
    effective_date: str = ""
    revision_date: str = ""
    source_url: str = ""
    note: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
    parts: list[PartRef] = []


class CompetitorSpecsResponse(BaseModel):
    company: CompetitorOut
    items: list[CompetitorSpecOut]
