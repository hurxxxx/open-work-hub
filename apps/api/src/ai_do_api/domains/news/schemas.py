"""Pydantic schemas for the news aggregator API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class NewsArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    keyword: str = ""
    source: str = ""
    date: str = ""
    title: str
    summary: str = ""
    original_url: str


class NewsListResponse(BaseModel):
    status: str = "success"
    channel: str
    collected_at: str | None = None
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    articles: list[NewsArticleOut]


class NewsSearchResponse(BaseModel):
    status: str = "success"
    query: str
    articles: list[NewsArticleOut]


class NewsArticleImage(BaseModel):
    url: str
    caption: str = ""


class NewsArticleDetail(BaseModel):
    status: str = "success"
    url: str
    full_text: str = ""
    summary: str = ""
    images: list[NewsArticleImage] = Field(default_factory=list)
    tables: list[str] = Field(default_factory=list)


class NewsFilterSettings(BaseModel):
    keyword_filter: list[str] = Field(default_factory=list)
    car_filter: list[str] = Field(default_factory=list)
    keyword_ui_filters: list[str] = Field(default_factory=list)


class NewsFilterUpdateRequest(BaseModel):
    keyword_filter: list[str] | None = None
    car_filter: list[str] | None = None
    keyword_ui_filters: list[str] | None = None


class NewsStatusResponse(BaseModel):
    collecting: bool = False
    collected_at: str | None = None
    is_today: bool = False


class NewsFetchResponse(BaseModel):
    status: str
    message: str


# ── 추천/스크랩 뉴스 ──
class NewsSnapshotRequest(BaseModel):
    channel: Literal["", "keyword", "front", "car"] = ""
    keyword: str = ""
    source: str = ""
    date: str = ""
    title: str
    summary: str = ""
    original_url: str


class NewsRecommendedArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str = ""
    keyword: str = ""
    source: str = ""
    date: str = ""
    title: str
    summary: str = ""
    original_url: str
    origin: str = "manual"
    reason: str = ""
    reason_detail: str = ""


class NewsRecommendedListResponse(BaseModel):
    status: str = "success"
    articles: list[NewsRecommendedArticleOut]


class NewsScrapArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    channel: str = ""
    keyword: str = ""
    source: str = ""
    date: str = ""
    title: str
    summary: str = ""
    original_url: str


class NewsScrapListResponse(BaseModel):
    status: str = "success"
    articles: list[NewsScrapArticleOut]


# ── AI 추천 뉴스 (큐레이션) ──
class NewsAiProfileResponse(BaseModel):
    ai_profile: str
    ai_profile_is_default: bool = False
    ai_curate_enabled: bool = True
    ai_curated_at: str | None = None


class NewsAiProfileUpdateRequest(BaseModel):
    ai_profile: str | None = None
    ai_curate_enabled: bool | None = None


class NewsCurateResponse(BaseModel):
    status: str = "success"
    evaluated: int = 0
    saved: int = 0
    by_reason: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
