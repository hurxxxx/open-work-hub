from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceBootstrapWorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str
    role: str


class WorkspaceBootstrapNavItemResponse(BaseModel):
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None
    coming_soon: bool = False


class WorkspaceBootstrapAppResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled: bool
    coming_soon: bool = False
    nav_items: list[WorkspaceBootstrapNavItemResponse]


class WorkspaceBootstrapAppBarCategoryItemResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: Literal["platform", "workspace"] = "workspace"
    enabled: bool
    coming_soon: bool = False
    position: int = 0


class WorkspaceBootstrapAppBarCategoryResponse(BaseModel):
    id: str
    key: str
    title: str
    icon_key: str
    position: int
    items: list[WorkspaceBootstrapAppBarCategoryItemResponse]


class WorkspaceBootstrapKeywordSearchEntityTypeResponse(BaseModel):
    value: str
    label: str
    label_key: str


class WorkspaceBootstrapKeywordSearchResponse(BaseModel):
    entity_types: list[WorkspaceBootstrapKeywordSearchEntityTypeResponse] = Field(
        default_factory=list
    )


class WorkspaceBootstrapResponse(BaseModel):
    workspace: WorkspaceBootstrapWorkspaceResponse
    apps: list[WorkspaceBootstrapAppResponse]
    app_bar_categories: list[WorkspaceBootstrapAppBarCategoryResponse] = Field(default_factory=list)
    nav: list[WorkspaceBootstrapNavItemResponse]
    platform_visible_app_ids: list[str] = Field(default_factory=list)
    chatbot_app_ids: list[str] = Field(default_factory=list)
    keyword_search: WorkspaceBootstrapKeywordSearchResponse = Field(
        default_factory=WorkspaceBootstrapKeywordSearchResponse
    )


__all__ = [
    "WorkspaceBootstrapAppBarCategoryItemResponse",
    "WorkspaceBootstrapAppBarCategoryResponse",
    "WorkspaceBootstrapAppResponse",
    "WorkspaceBootstrapNavItemResponse",
    "WorkspaceBootstrapKeywordSearchEntityTypeResponse",
    "WorkspaceBootstrapKeywordSearchResponse",
    "WorkspaceBootstrapResponse",
    "WorkspaceBootstrapWorkspaceResponse",
]
