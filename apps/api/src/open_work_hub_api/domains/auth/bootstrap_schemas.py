from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BootstrapNavItemResponse(BaseModel):
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None
    coming_soon: bool = False


class BootstrapAppResponse(BaseModel):
    entry_route_id: str
    execution_context_kind: Literal["personal", "company"]
    resource_scope: Literal["personal", "company", "hybrid"]
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled: bool
    coming_soon: bool = False
    nav_items: list[BootstrapNavItemResponse]


class BootstrapAppBarCategoryItemResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled: bool
    coming_soon: bool = False
    position: int = 0


class BootstrapAppBarCategoryResponse(BaseModel):
    id: str
    key: str
    title: str
    icon_key: str
    position: int
    items: list[BootstrapAppBarCategoryItemResponse]


class BootstrapKeywordSearchEntityTypeResponse(BaseModel):
    value: str
    label: str
    label_key: str


class BootstrapKeywordSearchResponse(BaseModel):
    entity_types: list[BootstrapKeywordSearchEntityTypeResponse] = Field(default_factory=list)


__all__ = [
    "BootstrapAppBarCategoryItemResponse",
    "BootstrapAppBarCategoryResponse",
    "BootstrapAppResponse",
    "BootstrapNavItemResponse",
    "BootstrapKeywordSearchEntityTypeResponse",
    "BootstrapKeywordSearchResponse",
]
