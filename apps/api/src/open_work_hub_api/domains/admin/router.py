from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
import re
import secrets
from typing import Any, Literal, get_args
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import delete as sa_delete
from sqlalchemy import and_, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.llm import get_allowed_external_llm_providers
from open_work_hub_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import (
    ensure_platform_app_visibility,
    ensure_workspace_app_entitlements,
    ensure_workspace_default_pms_space,
    is_platform_admin_user,
    is_valid_workspace_role,
    load_user_graph,
    load_active_workspace_by_id,
    normalize_locale,
    normalize_time_zone,
    normalize_workspace_role,
    replace_user_system_roles,
    record_audit_log,
    resolve_team_role,
    resolve_workspace_role,
    serialize_auth_user,
    slugify,
    team_role_allows,
    workspace_role_allows,
)
from open_work_hub_api.domains.auth.date_format_preferences import (
    default_date_format_value,
    normalize_date_format_payload,
    validate_date_format_value,
)
from open_work_hub_api.domains.auth.dependencies import (
    AuthContext,
    require_auth_context,
    require_permission,
)
from open_work_hub_api.domains.auth.models import (
    AuditLog,
    AuthSession,
    PlatformAppBarCategory,
    PlatformAppBarCategoryApp,
    PlatformAppVisibility,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceAppEntitlement,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.security import (
    derive_login_id_from_email,
    hash_password,
    is_valid_login_id,
    new_id,
    normalize_email,
    normalize_login_id,
)
from open_work_hub_api.domains.auth.session_lifecycle import revoke_active_user_sessions
from open_work_hub_api.domains.auth.workspace_apps import (
    get_workspace_app_catalog_item,
    iter_workspace_app_catalog,
)
from open_work_hub_api.domains.auth.app_bar_categories import (
    app_bar_category_app_ids_from_catalog,
    is_app_bar_category_app,
    is_platform_visibility_app,
)
from open_work_hub_api.domains.auth.workspace_app_features import (
    is_workspace_catalog_feature_enabled,
)
from open_work_hub_api.core.workspace_app_registry import WorkspaceAppCatalogItem
from open_work_hub_api.domains.ai.runtime.retention import scrub_completed_runtime_records
from open_work_hub_api.domains.ai.boundary_safety import (
    evaluate_external_payload_safety,
    known_content_origins,
    normalize_content_origin,
    normalize_external_safety_values,
)
from open_work_hub_api.domains.ai.privacy_filter import check_privacy_filter_health
from open_work_hub_api.domains.ai.masking import evaluate_external_payload_masking
from open_work_hub_api.domains.ai.models import (
    AiSecurityDetectedValue,
    AiSecurityExternalTransferException,
    AiSecurityPolicyRule,
)
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.ai.runtime.external_egress import (
    ExternalCapability,
    allowed_external_providers,
)
from open_work_hub_api.domains.ai.security_policy import (
    AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
    AI_SECURITY_LLM_CAPABILITY,
    CUSTOM_BLOCK_ENTITY_TYPE,
    DATA_PROTECTION_SETTINGS_ID,
    EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS,
    EXTERNAL_TRANSFER_EXCEPTION_REASON,
    HARD_EXTERNAL_TRANSFER_BLOCKERS,
    MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS,
    AiSecurityDataProtectionAction,
    AiSecurityExternalAppAction,
    AiSecurityExternalTransferExceptionDecision,
    AiSecurityExternalTransferBlocker,
    AiSecurityPolicyContext,
    AiSecurityPolicyEffect,
    ai_security_enforcement_enabled,
    ai_security_data_protection_blocker_actions,
    ai_security_external_app_action_for_blockers,
    ai_security_external_app_actions,
    evaluate_ai_security_policy,
    external_transfer_blockers_from_safety,
    get_ai_security_data_protection_settings,
    get_or_create_ai_security_data_protection_settings,
    hard_external_transfer_blockers,
    normalize_ai_security_effect,
    normalize_ai_security_blocker_actions,
    normalize_ai_security_external_app_actions,
    normalize_ai_security_task_kinds,
    normalize_custom_block_terms,
    normalize_external_transfer_blockers,
    resolve_ai_security_external_transfer_exception,
)
from open_work_hub_api.domains.admin.people_projection import admin_user_list_projection
from open_work_hub_api.domains.admin.workspace_members import (
    add_workspace_member_binding,
    apply_workspace_member_bulk_entry,
    list_workspace_member_directory,
    remove_workspace_member_binding,
    replace_workspace_member_bindings,
    serialize_workspace_member_binding,
    update_workspace_member_binding_role,
)
from open_work_hub_api.domains.admin.workspace_projection import admin_workspace_item_projection
from open_work_hub_api.domains.web_search.service import iter_web_search_external_app_profiles

AdminAppVisibilityScope = Literal["core"]
APP_BAR_ICON_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _invalid_workspace_role_error() -> PydanticCustomError:
    return PydanticCustomError(
        "admin.invalid_workspace_role",
        "Invalid workspace role.",
        {},
    )


def _valid_login_id_required_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.valid_login_id_required",
        "A valid ID is required.",
        {},
    )


class WorkspaceItemResponse(BaseModel):
    id: str
    key: str
    name: str
    description: str
    active: bool
    team_count: int
    member_count: int = 0
    meeting_count: int = 0
    doc_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceBindingItemResponse(BaseModel):
    subject_id: str
    subject_type: Literal["user"]
    subject_label: str
    subject_secondary: str | None = None
    role: str


class WorkspaceMemberCandidateResponse(BaseModel):
    id: str
    email: str
    full_name: str
    display_name: str
    status: str


class WorkspaceMemberItemResponse(BaseModel):
    subject_id: str
    subject_type: Literal["user"]
    subject_label: str
    subject_secondary: str | None = None
    role: str
    user_status: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class WorkspaceMemberRoleCounts(BaseModel):
    admin: int = 0
    member: int = 0


class AiRuntimeRetentionScrubResponse(BaseModel):
    scrubbed_run_count: int
    older_than_days: int


class WorkspaceMembersResponse(BaseModel):
    items: list[WorkspaceMemberItemResponse]
    total: int
    page: int
    page_size: int
    role_counts: WorkspaceMemberRoleCounts
    user_count: int
    pending_count: int


class TeamItemResponse(BaseModel):
    id: str
    workspace_id: str
    workspace_key: str
    key: str
    name: str
    description: str
    active: bool
    member_count: int
    current_user_role: str | None = None


class PlatformAppVisibleWorkspaceResponse(BaseModel):
    id: str
    key: str
    name: str


class PlatformAppVisibilityItemResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: Literal["platform", "workspace"] = "workspace"
    launcher_personal_tools: bool = False
    kind: str = "mode"
    visible: bool
    runtime_enabled: bool
    visible_workspace_count: int = 0
    visible_workspaces: list[PlatformAppVisibleWorkspaceResponse] = Field(
        default_factory=list,
    )
    updated_at: datetime | None = None


class PlatformAppVisibilityResponse(BaseModel):
    items: list[PlatformAppVisibilityItemResponse]


class WorkspaceAppVisibilityItemResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: Literal["workspace"] = "workspace"
    kind: str = "mode"
    platform_visible: bool
    visibility_override: bool | None = None
    effective_visible: bool
    runtime_enabled: bool
    updated_at: datetime | None = None


class WorkspaceAppVisibilityResponse(BaseModel):
    workspace_id: str
    workspace_key: str
    workspace_name: str
    items: list[WorkspaceAppVisibilityItemResponse]


class PlatformAppVisibilityUpdateItem(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=64)
    visible: bool


class PlatformAppVisibilityUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PlatformAppVisibilityUpdateItem] = Field(..., min_length=1, max_length=100)


class WorkspaceAppVisibilityUpdateItem(BaseModel):
    app_id: str = Field(..., min_length=1, max_length=64)
    visibility_override: bool | None = None


class WorkspaceAppVisibilityUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WorkspaceAppVisibilityUpdateItem] = Field(..., min_length=1, max_length=100)


class AdminAppBarCategoryAppItemResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    coming_soon: bool = False
    runtime_enabled: bool


class AdminAppBarCategoryResponse(BaseModel):
    id: str
    key: str
    title: str
    icon_key: str
    position: int
    items: list[AdminAppBarCategoryAppItemResponse] = Field(default_factory=list)
    updated_at: datetime | None = None


class AdminAppBarCategoriesResponse(BaseModel):
    categories: list[AdminAppBarCategoryResponse]
    available_apps: list[AdminAppBarCategoryAppItemResponse] = Field(
        default_factory=list,
    )
    icon_keys: list[str] = Field(default_factory=list)


class AdminAppBarCategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=120)
    icon_key: str = Field(..., min_length=1, max_length=64)
    position: int | None = Field(default=None, ge=0)

    @field_validator("title", "icon_key")
    @classmethod
    def strip_category_field(cls, value: str) -> str:
        return value.strip()


class AdminAppBarCategoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    icon_key: str | None = Field(default=None, min_length=1, max_length=64)
    position: int | None = Field(default=None, ge=0)

    @field_validator("title", "icon_key")
    @classmethod
    def strip_optional_category_field(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class AdminAppBarCategoryLayoutItem(BaseModel):
    id: str = Field(..., min_length=1, max_length=36)
    title: str = Field(..., min_length=1, max_length=120)
    icon_key: str = Field(..., min_length=1, max_length=64)
    app_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator("title", "icon_key")
    @classmethod
    def strip_layout_category_field(cls, value: str) -> str:
        return value.strip()


class AdminAppBarCategoryLayoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[AdminAppBarCategoryLayoutItem] = Field(..., max_length=100)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _serialize_workspace(db: Session, workspace: Workspace) -> WorkspaceItemResponse:
    return WorkspaceItemResponse.model_validate(admin_workspace_item_projection(db, workspace))


def _platform_app_visibility_rows_by_id(db: Session) -> dict[str, PlatformAppVisibility]:
    return {
        item.app_id: item
        for item in db.scalars(
            select(PlatformAppVisibility).order_by(PlatformAppVisibility.app_id.asc())
        ).all()
    }


def _catalog_items_for_platform_admin_app_scope(scope: AdminAppVisibilityScope):
    del scope
    catalog_items = tuple(iter_workspace_app_catalog())
    return tuple(app for app in catalog_items if is_platform_visibility_app(app))


def _catalog_items_for_workspace_admin_app_scope(scope: AdminAppVisibilityScope):
    del scope
    catalog_items = tuple(iter_workspace_app_catalog())
    return tuple(
        app
        for app in catalog_items
        if is_app_bar_category_app(app) and app.availability_scope == "workspace"
    )


def _serialize_platform_app_visibility(
    db: Session,
    *,
    scope: AdminAppVisibilityScope = "core",
) -> PlatformAppVisibilityResponse:
    rows_by_app_id = _platform_app_visibility_rows_by_id(db)
    catalog_items = tuple(iter_workspace_app_catalog())
    catalog_by_app_id = {app.app_id: app for app in catalog_items}
    active_workspaces = list(
        db.scalars(
            select(Workspace).where(Workspace.active.is_(True)).order_by(Workspace.name.asc())
        ).all()
    )
    active_workspace_ids = [workspace.id for workspace in active_workspaces]
    workspace_entitlements_by_id: dict[tuple[str, str], WorkspaceAppEntitlement] = {}
    if active_workspace_ids:
        workspace_entitlements_by_id = {
            (item.workspace_id, item.app_id): item
            for item in db.scalars(
                select(WorkspaceAppEntitlement).where(
                    WorkspaceAppEntitlement.workspace_id.in_(active_workspace_ids)
                )
            ).all()
        }

    def visible_for(app_id: str) -> bool:
        app = catalog_by_app_id[app_id]
        row = rows_by_app_id.get(app_id)
        return app.visible_by_default if row is None else bool(row.visible)

    runtime_cache: dict[str, bool] = {}

    def runtime_enabled_for(app_id: str) -> bool:
        if app_id in runtime_cache:
            return runtime_cache[app_id]
        app = catalog_by_app_id[app_id]
        runtime_enabled = visible_for(app_id) and _catalog_runtime_feature_enabled(app)
        runtime_cache[app_id] = bool(runtime_enabled)
        return runtime_cache[app_id]

    workspace_effective_cache: dict[tuple[str, str], bool] = {}

    def workspace_effective_visible_for(workspace_id: str, app_id: str) -> bool:
        cache_key = (workspace_id, app_id)
        if cache_key in workspace_effective_cache:
            return workspace_effective_cache[cache_key]
        app = catalog_by_app_id[app_id]
        entitlement = workspace_entitlements_by_id.get(cache_key)
        visibility_override = entitlement.visibility_override if entitlement is not None else None
        effective_visible = (
            bool(visibility_override)
            if visibility_override is not None
            else app.enabled_by_default and visible_for(app_id)
        )
        workspace_effective_cache[cache_key] = bool(effective_visible)
        return workspace_effective_cache[cache_key]

    workspace_runtime_cache: dict[tuple[str, str], bool] = {}

    def workspace_runtime_enabled_for(workspace_id: str, app_id: str) -> bool:
        cache_key = (workspace_id, app_id)
        if cache_key in workspace_runtime_cache:
            return workspace_runtime_cache[cache_key]
        app = catalog_by_app_id[app_id]
        runtime_enabled = workspace_effective_visible_for(
            workspace_id,
            app_id,
        ) and _catalog_runtime_feature_enabled(app)
        workspace_runtime_cache[cache_key] = bool(runtime_enabled)
        return workspace_runtime_cache[cache_key]

    def visible_workspaces_for(app_id: str) -> list[PlatformAppVisibleWorkspaceResponse]:
        if catalog_by_app_id[app_id].availability_scope == "platform":
            return []
        return [
            PlatformAppVisibleWorkspaceResponse(
                id=workspace.id,
                key=workspace.key,
                name=workspace.name,
            )
            for workspace in active_workspaces
            if workspace_runtime_enabled_for(workspace.id, app_id)
        ]

    def response_item_for(app: WorkspaceAppCatalogItem) -> PlatformAppVisibilityItemResponse:
        visible_workspaces = visible_workspaces_for(app.app_id)
        return PlatformAppVisibilityItemResponse(
            app_id=app.app_id,
            title=app.title,
            route_base=app.route_base,
            icon_key=app.icon_key,
            availability_scope=app.availability_scope,
            launcher_personal_tools=app.launcher_personal_tools,
            kind="launcher_app" if is_platform_visibility_app(app) else "mode",
            visible=visible_for(app.app_id),
            runtime_enabled=runtime_enabled_for(app.app_id),
            visible_workspace_count=len(visible_workspaces),
            visible_workspaces=visible_workspaces,
            updated_at=rows_by_app_id.get(app.app_id).updated_at
            if app.app_id in rows_by_app_id
            else None,
        )

    return PlatformAppVisibilityResponse(
        items=[response_item_for(app) for app in _catalog_items_for_platform_admin_app_scope(scope)]
    )


def _workspace_app_entitlement_rows_by_id(
    db: Session,
    workspace_id: str,
) -> dict[str, WorkspaceAppEntitlement]:
    return {
        item.app_id: item
        for item in db.scalars(
            select(WorkspaceAppEntitlement)
            .where(WorkspaceAppEntitlement.workspace_id == workspace_id)
            .order_by(WorkspaceAppEntitlement.app_id.asc())
        ).all()
    }


def _serialize_workspace_app_visibility(
    db: Session,
    workspace: Workspace,
    *,
    scope: AdminAppVisibilityScope = "core",
) -> WorkspaceAppVisibilityResponse:
    platform_rows_by_app_id = _platform_app_visibility_rows_by_id(db)
    entitlement_rows_by_app_id = _workspace_app_entitlement_rows_by_id(db, workspace.id)
    items: list[WorkspaceAppVisibilityItemResponse] = []
    all_catalog_items = tuple(iter_workspace_app_catalog())
    scoped_catalog_items = _catalog_items_for_workspace_admin_app_scope(scope)
    catalog_by_app_id = {app.app_id: app for app in all_catalog_items}

    def platform_visible_for(app_id: str) -> bool:
        app = catalog_by_app_id[app_id]
        platform_row = platform_rows_by_app_id.get(app_id)
        return app.visible_by_default if platform_row is None else bool(platform_row.visible)

    effective_cache: dict[str, bool] = {}

    def effective_visible_for(app_id: str) -> bool:
        if app_id in effective_cache:
            return effective_cache[app_id]
        app = catalog_by_app_id[app_id]
        entitlement = entitlement_rows_by_app_id.get(app_id)
        visibility_override = entitlement.visibility_override if entitlement is not None else None
        effective_visible = (
            bool(visibility_override)
            if visibility_override is not None
            else app.enabled_by_default and platform_visible_for(app_id)
        )
        effective_cache[app_id] = bool(effective_visible)
        return effective_cache[app_id]

    runtime_cache: dict[str, bool] = {}

    def runtime_enabled_for(app_id: str) -> bool:
        if app_id in runtime_cache:
            return runtime_cache[app_id]
        app = catalog_by_app_id[app_id]
        runtime_enabled = effective_visible_for(app_id) and _catalog_runtime_feature_enabled(app)
        runtime_cache[app_id] = bool(runtime_enabled)
        return runtime_cache[app_id]

    for app in scoped_catalog_items:
        entitlement = entitlement_rows_by_app_id.get(app.app_id)
        platform_visible = platform_visible_for(app.app_id)
        visibility_override = entitlement.visibility_override if entitlement is not None else None
        effective_visible = effective_visible_for(app.app_id)
        items.append(
            WorkspaceAppVisibilityItemResponse(
                app_id=app.app_id,
                title=app.title,
                route_base=app.route_base,
                icon_key=app.icon_key,
                availability_scope="workspace",
                kind="launcher_app" if is_app_bar_category_app(app) else "mode",
                platform_visible=platform_visible,
                visibility_override=visibility_override,
                effective_visible=effective_visible,
                runtime_enabled=runtime_enabled_for(app.app_id),
                updated_at=entitlement.updated_at if entitlement is not None else None,
            )
        )

    return WorkspaceAppVisibilityResponse(
        workspace_id=workspace.id,
        workspace_key=workspace.key,
        workspace_name=workspace.name,
        items=items,
    )


def _app_bar_category_rows(db: Session) -> list[PlatformAppBarCategory]:
    return list(
        db.scalars(
            select(PlatformAppBarCategory)
            .options(selectinload(PlatformAppBarCategory.apps))
            .order_by(
                PlatformAppBarCategory.position.asc(),
                PlatformAppBarCategory.key.asc(),
            )
        ).all()
    )


def _app_bar_category_base_rows(db: Session) -> list[PlatformAppBarCategory]:
    return list(
        db.scalars(
            select(PlatformAppBarCategory).order_by(
                PlatformAppBarCategory.position.asc(),
                PlatformAppBarCategory.key.asc(),
            )
        ).all()
    )


def _app_bar_category_target_catalog_items() -> dict[str, WorkspaceAppCatalogItem]:
    catalog_items = tuple(iter_workspace_app_catalog())
    target_app_ids = app_bar_category_app_ids_from_catalog(catalog_items)
    return {app.app_id: app for app in catalog_items if app.app_id in target_app_ids}


def _valid_app_bar_icon_keys() -> set[str]:
    return {
        "activity",
        "bar-chart-3",
        "book-open",
        "briefcase",
        "database",
        "files",
        "folder-kanban",
        "history",
        "layout",
        "message-square",
        "plug",
        "search",
        "settings",
        "sparkles",
        "star",
        "users",
        "wrench",
        *(app.icon_key for app in iter_workspace_app_catalog()),
    }


def _ensure_valid_app_bar_icon_key(icon_key: str) -> None:
    if not APP_BAR_ICON_KEY_PATTERN.fullmatch(icon_key):
        raise localized_http_exception(
            status_code=400,
            code="admin.invalid_app_bar_icon",
            icon_key=icon_key,
        )


def _serialize_app_bar_category_item(
    app: WorkspaceAppCatalogItem,
) -> AdminAppBarCategoryAppItemResponse:
    return AdminAppBarCategoryAppItemResponse(
        app_id=app.app_id,
        title=app.title,
        route_base=app.route_base,
        icon_key=app.icon_key,
        coming_soon=app.coming_soon,
        runtime_enabled=_catalog_runtime_feature_enabled(app),
    )


def _serialize_admin_app_bar_categories(db: Session) -> AdminAppBarCategoriesResponse:
    target_items_by_app_id = _app_bar_category_target_catalog_items()
    rows = _app_bar_category_rows(db)
    assigned_app_ids: set[str] = set()
    categories: list[AdminAppBarCategoryResponse] = []

    for row in rows:
        items: list[AdminAppBarCategoryAppItemResponse] = []
        for app_row in sorted(row.apps, key=lambda item: (item.position, item.app_id)):
            app_id = app_row.app_id
            app = target_items_by_app_id.get(app_id)
            if app is None:
                continue
            assigned_app_ids.add(app_id)
            items.append(_serialize_app_bar_category_item(app))
        categories.append(
            AdminAppBarCategoryResponse(
                id=row.id,
                key=row.key,
                title=row.title,
                icon_key=row.icon_key,
                position=row.position,
                items=items,
                updated_at=row.updated_at,
            )
        )

    available_apps = [
        _serialize_app_bar_category_item(app)
        for _app_id, app in sorted(target_items_by_app_id.items())
    ]
    return AdminAppBarCategoriesResponse(
        categories=categories,
        available_apps=available_apps,
        icon_keys=sorted(_valid_app_bar_icon_keys()),
    )


def _next_app_bar_category_key(db: Session) -> str:
    existing_keys = set(db.scalars(select(PlatformAppBarCategory.key)).all())
    while True:
        key = new_id()
        if key not in existing_keys:
            return key


def _max_app_bar_category_position(db: Session) -> int:
    value = db.scalar(select(func.max(PlatformAppBarCategory.position)))
    return int(value) if value is not None else -1


def _app_bar_category_by_id(db: Session, category_id: str) -> PlatformAppBarCategory:
    row = db.get(PlatformAppBarCategory, category_id)
    if row is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.app_bar_category_not_found",
            category_id=category_id,
        )
    return row


def _catalog_runtime_feature_enabled(app: WorkspaceAppCatalogItem) -> bool:
    return app.feature_flag is None or is_workspace_catalog_feature_enabled(
        get_settings(),
        app.feature_flag,
    )


def _ensure_platform_admin(context: AuthContext, db: Session) -> None:
    if not is_platform_admin_user(context.user, db):
        raise localized_http_exception(status_code=403, code="admin.platform_admin_required")


def _get_active_team(
    db: Session,
    team_id: str,
    *,
    include_workspace: bool = False,
    include_members: bool = False,
) -> Team | None:
    query = select(Team).where(
        Team.id == team_id,
        Team.trashed_at.is_(None),
    )
    if include_workspace:
        query = query.options(joinedload(Team.workspace))
    if include_members:
        query = query.options(selectinload(Team.members))
    return db.scalar(query)


def _ensure_workspace_scope(
    db: Session,
    user: User,
    workspace_id: str,
    *,
    min_role: str = "member",
) -> Workspace:
    workspace = load_active_workspace_by_id(db, workspace_id)
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    if is_platform_admin_user(user, db):
        return workspace

    role = resolve_workspace_role(db, user, workspace.id)
    if not workspace_role_allows(role, min_role):
        raise localized_http_exception(status_code=403, code="workspace.access_required")
    return workspace


def _ensure_admin_workspace_scope(
    db: Session,
    user: User,
    workspace_id: str,
) -> Workspace:
    """Like `_ensure_workspace_scope` but allows archived (active=false) workspaces.

    Used by admin endpoints that need to manage soft-deleted workspaces.
    Only platform admins or workspace admin role holders pass.
    """
    workspace = db.scalar(
        select(Workspace).options(selectinload(Workspace.teams)).where(Workspace.id == workspace_id)
    )
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    if is_platform_admin_user(user, db):
        return workspace
    role = resolve_workspace_role(db, user, workspace.id)
    if not workspace_role_allows(role, "admin"):
        raise localized_http_exception(status_code=403, code="workspace.access_required")
    return workspace


def _ensure_team_scope(
    db: Session,
    user: User,
    team_id: str,
    *,
    min_role: str = "member",
    include_workspace: bool = False,
    include_members: bool = False,
) -> Team:
    team = _get_active_team(
        db,
        team_id,
        include_workspace=include_workspace,
        include_members=include_members,
    )
    if team is None or not team.active or not team.workspace.active:
        raise localized_http_exception(status_code=404, code="team.not_found")
    if is_platform_admin_user(user, db):
        return team
    role = resolve_team_role(db, user, team)
    if not team_role_allows(role, min_role):
        raise localized_http_exception(status_code=403, code="team.access_required")
    return team


class AuditLogItemResponse(BaseModel):
    id: str
    actor_user_id: str | None
    actor_name: str | None
    action: str
    entity_kind: str
    entity_id: str | None
    summary: str
    payload: dict[str, object]
    created_at: str


class AuditLogsResponse(BaseModel):
    items: list[AuditLogItemResponse]
    total: int
    limit: int
    offset: int
    next_offset: int | None


class AdminUsageTotalsResponse(BaseModel):
    user_count: int
    active_user_count: int
    today_visitor_count: int
    inactive_user_count: int
    login_count: int
    audit_event_count: int
    app_open_count: int
    content_view_count: int
    search_query_count: int
    content_created_count: int
    docs_view_count: int
    docs_owned_count: int
    docs_created_count: int
    whiteboards_view_count: int
    whiteboards_owned_count: int
    whiteboards_created_count: int
    meetings_created_count: int
    pms_tasks_created_count: int
    llm_call_count: int
    llm_user_count: int
    llm_success_count: int
    llm_error_count: int
    llm_cancelled_count: int
    llm_total_tokens: int
    llm_prompt_tokens: int
    llm_completion_tokens: int
    llm_average_latency_ms: int | None = None


class AdminUsageBreakdownItemResponse(BaseModel):
    key: str
    label: str
    count: int
    total_tokens: int = 0


class AdminUsageTrendPointResponse(BaseModel):
    date: str
    visitor_count: int
    active_user_count: int


class AdminUsageHourlyPointResponse(BaseModel):
    hour: int
    login_count: int
    visitor_count: int
    average_login_count: float
    average_visitor_count: float


class AdminUsageTokenRankItemResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    llm_call_count: int
    llm_total_tokens: int


class AdminUsagePmsSummaryResponse(BaseModel):
    project_count: int
    stakeholder_count: int
    attachment_count: int
    attachment_total_bytes: int
    active_user_count: int
    task_activity_count: int
    task_comment_count: int
    attachment_added_count: int


class AdminUsageAiConnectionItemResponse(BaseModel):
    pool: str
    provider: str
    status: str
    ready: bool
    model: str
    canonical_model: str
    detail: str | None = None


class AdminUsageAiTeamSummaryResponse(BaseModel):
    connections: list[AdminUsageAiConnectionItemResponse]
    suggestion_count: int
    unanswered_suggestion_count: int


class AdminUsageTargetScopeResponse(BaseModel):
    configured: bool
    user_count: int
    explicit_user_count: int


class AdminUsageTargetUserItemResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    targeted_at: str


class AdminUsageTargetsResponse(BaseModel):
    users: list[AdminUsageTargetUserItemResponse]
    resolved_user_count: int


class AdminUsageTargetsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(default_factory=list, max_length=500)


class AdminUsageUserItemResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    last_login_at: str | None = None
    login_count: int = 0
    audit_event_count: int = 0
    app_open_count: int = 0
    content_view_count: int = 0
    search_query_count: int = 0
    docs_view_count: int = 0
    docs_owned_count: int = 0
    docs_created_count: int = 0
    whiteboards_view_count: int = 0
    whiteboards_owned_count: int = 0
    whiteboards_created_count: int = 0
    meetings_created_count: int = 0
    pms_tasks_created_count: int = 0
    llm_call_count: int = 0
    llm_total_tokens: int = 0
    llm_average_latency_ms: int | None = None
    activity_score: int = 0


class AdminUsageDashboardResponse(BaseModel):
    period_days: int
    from_date: date
    to_date: date
    generated_at: str
    target_scope: AdminUsageTargetScopeResponse
    totals: AdminUsageTotalsResponse
    users: list[AdminUsageUserItemResponse]
    daily_trends: list[AdminUsageTrendPointResponse]
    hourly_access: list[AdminUsageHourlyPointResponse]
    token_rankings: list[AdminUsageTokenRankItemResponse]
    usage_by_app: list[AdminUsageBreakdownItemResponse]
    usage_by_route: list[AdminUsageBreakdownItemResponse]
    content_views_by_kind: list[AdminUsageBreakdownItemResponse]
    llm_by_task_kind: list[AdminUsageBreakdownItemResponse]
    llm_by_model: list[AdminUsageBreakdownItemResponse]
    pms_summary: AdminUsagePmsSummaryResponse
    ai_team_summary: AdminUsageAiTeamSummaryResponse
    recent_audit_logs: list[AuditLogItemResponse]


class AdminUsageExcludedUserItemResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    excluded_at: str


class AdminUsageExcludedUsersUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ids: list[str] = Field(default_factory=list, max_length=500)


class AiSecurityExternalAppCandidateResponse(BaseModel):
    app_id: str
    app_label: str | None = None
    task_kind: str
    capability: str
    provider: str
    description: str


class AiSecurityDataProtectionResponse(BaseModel):
    enforcement_enabled: bool
    enforcement_disabled_reason: str
    custom_block_terms: list[str]
    mandatory_blockers: list[str]
    hard_blockers: list[AiSecurityExternalTransferBlocker]
    exception_eligible_blockers: list[AiSecurityExternalTransferBlocker]
    mask_eligible_blockers: list[AiSecurityExternalTransferBlocker]
    blocker_actions: dict[str, AiSecurityDataProtectionAction]
    external_app_actions: dict[str, dict[str, AiSecurityExternalAppAction]]
    privacy_filter_enabled: bool
    privacy_filter_ready: bool
    privacy_filter_status: str
    privacy_filter_checkpoint: str
    privacy_filter_detail: str | None = None
    privacy_filter_device: str
    updated_at: str | None = None
    updated_by: str | None = None


class AiSecurityDataProtectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    custom_block_terms: list[str] = Field(default_factory=list, max_length=200)
    blocker_actions: dict[str, AiSecurityDataProtectionAction] = Field(default_factory=dict)
    external_app_actions: dict[str, dict[str, AiSecurityExternalAppAction]] = Field(
        default_factory=dict
    )

    @field_validator("custom_block_terms")
    @classmethod
    def _normalize_terms(cls, value: list[str]) -> list[str]:
        return normalize_custom_block_terms(value)

    @field_validator("blocker_actions", mode="before")
    @classmethod
    def _normalize_blocker_actions(cls, value: object) -> dict[str, AiSecurityDataProtectionAction]:
        return normalize_ai_security_blocker_actions(value)

    @field_validator("external_app_actions", mode="before")
    @classmethod
    def _normalize_external_app_actions(
        cls,
        value: object,
    ) -> dict[str, dict[str, AiSecurityExternalAppAction]]:
        return normalize_ai_security_external_app_actions(value)


class AiSecurityEnforcementUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enforcement_enabled: bool
    enforcement_disabled_reason: str = Field(default="", max_length=500)


class AiSecurityPolicyRuleResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    user_id: str | None = None
    user_name: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    app_id: str | None = None
    task_kind: str | None = None
    task_kinds: list[str] = Field(default_factory=list)
    capability: str | None = None
    provider: str | None = None
    effect: AiSecurityPolicyEffect
    custom_block_terms: list[str]
    created_at: str
    updated_at: str


class AiSecurityPolicyRuleUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    user_id: str | None = Field(default=None, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    app_id: str | None = Field(default=None, max_length=64)
    task_kind: str | None = Field(default=None, max_length=128)
    task_kinds: list[str] = Field(default_factory=list, max_length=50)
    capability: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    effect: AiSecurityPolicyEffect = "inherit"
    custom_block_terms: list[str] = Field(default_factory=list, max_length=200)

    @field_validator(
        "name",
        "user_id",
        "workspace_id",
        "app_id",
        "task_kind",
        "capability",
        "provider",
        mode="before",
    )
    @classmethod
    def _strip_optional_strings(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("app_id")
    @classmethod
    def _normalize_app_id(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @field_validator("task_kind", "capability", "provider")
    @classmethod
    def _normalize_scope_tokens(cls, value: str | None) -> str | None:
        return value.strip().lower().replace("-", "_") if value else None

    @field_validator("task_kinds")
    @classmethod
    def _normalize_task_kinds(cls, value: list[str]) -> list[str]:
        return normalize_ai_security_task_kinds(value)

    @field_validator("effect", mode="before")
    @classmethod
    def _normalize_effect(cls, value: object) -> AiSecurityPolicyEffect:
        return normalize_ai_security_effect(value)

    @field_validator("custom_block_terms")
    @classmethod
    def _normalize_rule_terms(cls, value: list[str]) -> list[str]:
        return normalize_custom_block_terms(value)

    @model_validator(mode="after")
    def _apply_task_kind_compatibility(self) -> "AiSecurityPolicyRuleUpsertRequest":
        task_kinds = normalize_ai_security_task_kinds(self.task_kinds)
        if not task_kinds and self.task_kind:
            task_kinds = normalize_ai_security_task_kinds([self.task_kind])
        self.task_kinds = task_kinds
        self.task_kind = task_kinds[0] if len(task_kinds) == 1 else None
        return self


class AiSecurityPolicyRulesResponse(BaseModel):
    items: list[AiSecurityPolicyRuleResponse]


class AiSecurityExternalTransferExceptionResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    user_id: str | None = None
    user_name: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    app_id: str | None = None
    task_kind: str | None = None
    task_kinds: list[str] = Field(default_factory=list)
    capability: str | None = None
    provider: str | None = None
    allowed_blocker_types: list[AiSecurityExternalTransferBlocker]
    reason: str
    expires_at: str | None = None
    created_at: str
    updated_at: str


class AiSecurityExternalTransferExceptionUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    enabled: bool = True
    user_id: str | None = Field(default=None, max_length=36)
    workspace_id: str | None = Field(default=None, max_length=36)
    app_id: str | None = Field(default=None, max_length=64)
    task_kind: str | None = Field(default=None, max_length=128)
    task_kinds: list[str] = Field(default_factory=list, max_length=50)
    capability: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    allowed_blocker_types: list[AiSecurityExternalTransferBlocker] = Field(
        default_factory=list,
        max_length=10,
    )
    reason: str = Field(min_length=1, max_length=1000)
    expires_at: datetime | None = None

    @field_validator(
        "name",
        "user_id",
        "workspace_id",
        "app_id",
        "task_kind",
        "capability",
        "provider",
        mode="before",
    )
    @classmethod
    def _strip_optional_strings(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("description", "reason")
    @classmethod
    def _strip_long_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("app_id")
    @classmethod
    def _normalize_app_id(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @field_validator("task_kind", "capability", "provider")
    @classmethod
    def _normalize_scope_tokens(cls, value: str | None) -> str | None:
        return value.strip().lower().replace("-", "_") if value else None

    @field_validator("task_kinds")
    @classmethod
    def _normalize_task_kinds(cls, value: list[str]) -> list[str]:
        return normalize_ai_security_task_kinds(value)

    @field_validator("allowed_blocker_types")
    @classmethod
    def _normalize_allowed_blockers(
        cls,
        value: list[AiSecurityExternalTransferBlocker],
    ) -> list[AiSecurityExternalTransferBlocker]:
        normalized = normalize_external_transfer_blockers(value)
        unsupported = [
            blocker
            for blocker in normalized
            if blocker not in EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
        ]
        if unsupported:
            raise PydanticCustomError(
                "ai_security_hard_blocker_exception",
                "Hard blockers cannot be used in external transfer exceptions.",
            )
        return normalized  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_exception_scope(self) -> "AiSecurityExternalTransferExceptionUpsertRequest":
        if not self.allowed_blocker_types:
            raise PydanticCustomError(
                "ai_security_exception_blocker_required",
                "At least one exception-eligible blocker is required.",
            )
        if not self.reason.strip():
            raise PydanticCustomError(
                "ai_security_exception_reason_required",
                "A reason is required.",
            )
        if self.expires_at is None:
            raise PydanticCustomError(
                "ai_security_exception_expiry_required",
                "An expiration time is required.",
            )
        expiry = (
            self.expires_at.astimezone(UTC).replace(tzinfo=None)
            if self.expires_at.tzinfo is not None
            else self.expires_at
        )
        if expiry <= datetime.now(UTC).replace(tzinfo=None):
            raise PydanticCustomError(
                "ai_security_exception_expired",
                "Expiration time must be in the future.",
            )
        return self

    @model_validator(mode="after")
    def _apply_task_kind_compatibility(self) -> "AiSecurityExternalTransferExceptionUpsertRequest":
        task_kinds = normalize_ai_security_task_kinds(self.task_kinds)
        if not task_kinds and self.task_kind:
            task_kinds = normalize_ai_security_task_kinds([self.task_kind])
        self.task_kinds = task_kinds
        self.task_kind = task_kinds[0] if len(task_kinds) == 1 else None
        return self


class AiSecurityExternalTransferExceptionsResponse(BaseModel):
    items: list[AiSecurityExternalTransferExceptionResponse]


class AiSecurityConditionOptionResponse(BaseModel):
    value: str
    label: str | None = None


class AiSecurityConditionOptionsResponse(BaseModel):
    apps: list[AiSecurityConditionOptionResponse]
    external_apps: list[AiSecurityConditionOptionResponse] = Field(default_factory=list)
    task_kinds: list[AiSecurityConditionOptionResponse]
    capabilities: list[AiSecurityConditionOptionResponse]
    providers: list[AiSecurityConditionOptionResponse]
    content_origins: list[AiSecurityConditionOptionResponse]


class AiSecuritySummaryResponse(BaseModel):
    external_app_candidates: list[AiSecurityExternalAppCandidateResponse] = Field(
        default_factory=list
    )
    data_protection: AiSecurityDataProtectionResponse
    rules: list[AiSecurityPolicyRuleResponse]
    exceptions: list[AiSecurityExternalTransferExceptionResponse]
    condition_options: AiSecurityConditionOptionsResponse
    active_rule_count: int
    active_exception_count: int
    audit_log_count_24h: int


class AiSecurityMonitoringTotalsResponse(BaseModel):
    security_event_count: int
    blocked_event_count: int
    forced_local_count: int
    masked_event_count: int
    external_exception_count: int
    hard_blocker_count: int
    unique_actor_count: int


class AiSecurityMonitoringTrendPointResponse(BaseModel):
    date: str
    blocked_count: int
    forced_local_count: int
    masked_count: int


class AiSecurityMonitoringBreakdownItemResponse(BaseModel):
    key: str
    label: str
    count: int


class AiSecurityMonitoringUserItemResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    blocked_count: int
    forced_local_count: int
    masked_count: int
    total_count: int
    last_blocked_at: str | None = None


class AiSecurityDetectedValueStatResponse(BaseModel):
    detector: str
    entity_type: str
    blocker_type: str
    detected_value: str | None = None
    value_hash: str | None = None
    occurrence_count: int
    event_count: int


class AiSecurityDetectedValueGroupResponse(BaseModel):
    detector: str
    entity_type: str
    blocker_type: str
    occurrence_count: int
    event_count: int
    distinct_value_count: int
    latest_at: str | None = None
    detail_available: bool


class AiSecurityDetectedValueGroupsResponse(BaseModel):
    items: list[AiSecurityDetectedValueGroupResponse]
    total: int
    limit: int
    offset: int


class AiSecurityDetectedValueDetailsResponse(BaseModel):
    items: list[AiSecurityDetectedValueStatResponse]
    total: int
    limit: int
    offset: int


class AiSecurityMonitoringResponse(BaseModel):
    period_days: int
    from_date: date
    to_date: date
    generated_at: str
    totals: AiSecurityMonitoringTotalsResponse
    daily_trends: list[AiSecurityMonitoringTrendPointResponse]
    blocked_by_user: list[AiSecurityMonitoringUserItemResponse]
    blocked_by_reason: list[AiSecurityMonitoringBreakdownItemResponse]
    blocked_by_entity_type: list[AiSecurityMonitoringBreakdownItemResponse]
    detected_value_groups: list[AiSecurityDetectedValueGroupResponse]
    privacy_filter_groups: list[AiSecurityDetectedValueGroupResponse]
    detected_value_rankings: list[AiSecurityDetectedValueStatResponse]
    privacy_filter_rankings: list[AiSecurityDetectedValueStatResponse]
    blocked_events: list[AuditLogItemResponse]


class AiSecuritySimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str | None = Field(default=None, max_length=36)
    actor_user_id: str | None = Field(default=None, max_length=36)
    app_id: str | None = Field(default=None, max_length=64)
    task_kind: str | None = Field(default=None, max_length=128)
    capability: str | None = Field(default=None, max_length=128)
    provider: str | None = Field(default=None, max_length=64)
    content_origin: str | None = Field(default=None, max_length=64)
    source_kinds: list[str] = Field(default_factory=list, max_length=20)
    sensitivity_labels: list[str] = Field(default_factory=list, max_length=20)
    sample_text: str | None = Field(default=None, max_length=2000)


class AiSecuritySimulationResponse(BaseModel):
    effect: AiSecurityPolicyEffect
    rule_id: str | None = None
    rule_name: str | None = None
    reason_code: str
    route_action: Literal[
        "unchanged",
        "blocked",
        "audit_only",
        "external_exception",
        "masked_external",
    ]
    allow_external: bool
    forced_local: bool
    blocked_entity_types: list[str]
    external_transfer_blocker_types: list[AiSecurityExternalTransferBlocker]
    hard_blocker_types: list[AiSecurityExternalTransferBlocker]
    external_transfer_exception_allowed: bool
    external_transfer_exception_id: str | None = None
    external_transfer_exception_name: str | None = None
    external_transfer_exception_reason: str | None = None
    pii_hits: list[str]
    sensitivity_labels: list[str]
    content_origin: str
    source_kinds: list[str]
    custom_block_term_count: int
    matched_scope: dict[str, str]
    mask_applied: bool = False
    masked_entity_types: list[str] = Field(default_factory=list)
    masked_text_preview: str | None = None
    privacy_filter_status: str | None = None


class AdminUserItemResponse(BaseModel):
    id: str
    login_id: str
    email: str
    full_name: str
    display_name: str
    status: str
    login_blocked: bool
    theme_preference: str
    locale: str
    time_zone: str
    date_format: str
    system_roles: list[str]
    workspaces: list[dict[str, object]]
    workspace_roles: list[dict[str, str]]
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUsersResponse(BaseModel):
    items: list[AdminUserItemResponse]
    total: int
    page: int
    page_size: int


class CreatedUserResponse(BaseModel):
    user: AdminUserItemResponse
    temporary_password: str


class WorkspaceUpsertRequest(BaseModel):
    key: str | None = Field(default=None, max_length=48)
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    active: bool = True


class TeamUpsertRequest(BaseModel):
    key: str | None = Field(default=None, max_length=48)
    name: str = Field(..., min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    active: bool = True


class WorkspaceBindingInput(BaseModel):
    subject_id: str
    role: str = Field(default="member", max_length=24)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if not is_valid_workspace_role(value):
            raise _invalid_workspace_role_error()
        normalized = normalize_workspace_role(value)
        assert normalized is not None
        return normalized


class WorkspaceBindingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    users: list[WorkspaceBindingInput] = Field(default_factory=list)


class WorkspaceMemberUpsertRequest(BaseModel):
    subject_id: str
    subject_type: Literal["user"]
    role: str = Field(default="member", max_length=24)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if not is_valid_workspace_role(value):
            raise _invalid_workspace_role_error()
        normalized = normalize_workspace_role(value)
        assert normalized is not None
        return normalized


class WorkspaceMemberRoleUpdateRequest(BaseModel):
    role: str = Field(..., max_length=24)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if not is_valid_workspace_role(value):
            raise _invalid_workspace_role_error()
        normalized = normalize_workspace_role(value)
        assert normalized is not None
        return normalized


class WorkspaceMemberBulkSubject(BaseModel):
    subject_type: Literal["user"]
    subject_id: str
    role: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_workspace_role(value):
            raise _invalid_workspace_role_error()
        return normalize_workspace_role(value)


class WorkspaceMemberBulkRequest(BaseModel):
    action: Literal["add", "remove", "update_role"]
    subjects: list[WorkspaceMemberBulkSubject] = Field(..., min_length=1, max_length=200)


class WorkspaceMemberBulkResponse(BaseModel):
    succeeded: int
    failed: list[dict[str, str]] = Field(default_factory=list)


class TeamMembersUpdateRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class AdminUserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login_id: str | None = Field(default=None, min_length=3, max_length=40)
    email: str = Field(..., min_length=5, max_length=320)
    full_name: str = Field(..., min_length=2, max_length=120)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    system_roles: list[str] = Field(default_factory=list)
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    status: Literal["active", "invited", "suspended"] = "active"
    locale: Literal["ko-KR", "en-US"] | None = None
    time_zone: str | None = Field(default=None, min_length=1, max_length=64)
    date_format: Literal["korean", "iso", "us", "european", "locale"] | None = None

    @field_validator("login_id", mode="before")
    @classmethod
    def validate_login_id(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        normalized = normalize_login_id(value)
        if not is_valid_login_id(normalized):
            raise _valid_login_id_required_error()
        return normalized

    @model_validator(mode="before")
    @classmethod
    def validate_date_format_before_field_types(cls, data):
        return normalize_date_format_payload(data)

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_time_zone(value)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_locale(value)

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        return validate_date_format_value(value)


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    system_roles: list[str] | None = None
    status: Literal["active", "invited", "suspended"] | None = None
    login_blocked: bool | None = None
    theme_preference: Literal["system", "light", "dark"] | None = None
    locale: Literal["ko-KR", "en-US"] | None = None
    time_zone: str | None = Field(default=None, min_length=1, max_length=64)
    date_format: Literal["korean", "iso", "us", "european", "locale"] | None = None
    must_change_password: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_date_format_before_field_types(cls, data):
        return normalize_date_format_payload(data)

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_time_zone(value)

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_locale(value)

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        return validate_date_format_value(value)


class ResetPasswordRequest(BaseModel):
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    temporary_password: str


router = APIRouter(prefix="/admin", tags=["admin"])
USAGE_DASHBOARD_TIME_ZONE = ZoneInfo("Asia/Seoul")
MAX_USAGE_DASHBOARD_RANGE_DAYS = 366
MAX_AUDIT_LOG_RANGE_DAYS = 3650
ADMIN_USER_LIST_OPTIONS = (
    selectinload(User.system_role_links),
    selectinload(User.workspace_bindings).joinedload(WorkspaceUserBinding.workspace),
)


def _request_locale(request: Request) -> str:
    return select_locale(
        explicit_locale=request.headers.get("x-open-work-hub-locale"),
        accept_language=request.headers.get("accept-language"),
    )


def _exception_code(exc: HTTPException) -> str | None:
    if isinstance(exc.detail, LocalizedApiMessage):
        return exc.detail.code
    return None


def _exception_detail(exc: HTTPException, request: Request) -> str:
    if isinstance(exc.detail, LocalizedApiMessage):
        return translate_message(exc.detail, _request_locale(request))
    return str(exc.detail)


def _generate_temporary_password() -> str:
    return f"Open Work Hub!{secrets.token_urlsafe(10)}"


def _make_unique_login_id(db: Session, base_login_id: str) -> str:
    base = base_login_id[:40].strip("._-") or "user"
    candidate = base
    suffix = 2
    while db.scalar(select(User.id).where(User.login_id == candidate)) is not None:
        suffix_text = f"-{suffix}"
        candidate = f"{base[: 40 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _serialize_admin_user(db: Session, user: User) -> AdminUserItemResponse:
    loaded = load_user_graph(db, user.id)
    if loaded is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    return AdminUserItemResponse.model_validate(serialize_auth_user(db, loaded))


def _resolve_docs_native_user_ids(db: Session, user_ids: set[str]) -> set[str]:
    if not user_ids:
        return set()

    from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocUserShare

    owner_ids = set(
        db.scalars(
            select(NativeDoc.owner_id).where(
                NativeDoc.owner_id.in_(user_ids),
                NativeDoc.trashed_at.is_(None),
            )
        )
    )
    shared_user_ids = set(
        db.scalars(
            select(NativeDocUserShare.user_id)
            .join(NativeDoc, NativeDoc.id == NativeDocUserShare.doc_id)
            .where(
                NativeDocUserShare.user_id.in_(user_ids),
                NativeDoc.trashed_at.is_(None),
            )
        )
    )
    return owner_ids | shared_user_ids


def _serialize_admin_user_list(db: Session, users: list[User]) -> list[AdminUserItemResponse]:
    return [
        AdminUserItemResponse.model_validate(item) for item in admin_user_list_projection(db, users)
    ]


def _serialize_audit_log_item(item: AuditLog) -> AuditLogItemResponse:
    return AuditLogItemResponse(
        id=item.id,
        actor_user_id=item.actor_user_id,
        actor_name=item.actor.full_name if item.actor else None,
        action=item.action,
        entity_kind=item.entity_kind,
        entity_id=item.entity_id,
        summary=item.summary,
        payload=item.payload or {},
        created_at=item.created_at.isoformat(),
    )


def _ai_security_mandatory_blockers() -> list[str]:
    return [
        "internal_context",
        "blocking_sensitivity_label",
        "pii",
        "credential",
        "internal_url",
        "security_document",
        "sensitive_identifier",
    ]


def _ai_security_hard_blockers() -> list[AiSecurityExternalTransferBlocker]:
    ordered: list[AiSecurityExternalTransferBlocker] = [
        "credential",
        "custom_block_term",
        "unknown_external_entity",
    ]
    return [blocker for blocker in ordered if blocker in HARD_EXTERNAL_TRANSFER_BLOCKERS]


def _ai_security_exception_eligible_blockers() -> list[AiSecurityExternalTransferBlocker]:
    ordered: list[AiSecurityExternalTransferBlocker] = [
        "internal_context",
        "blocking_sensitivity_label",
        "sensitive_identifier",
        "policy_block_external",
        "pii",
        "internal_url",
        "security_document",
    ]
    return [
        blocker for blocker in ordered if blocker in EXCEPTION_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS
    ]


def _ai_security_mask_eligible_blockers() -> list[AiSecurityExternalTransferBlocker]:
    ordered: list[AiSecurityExternalTransferBlocker] = [
        "sensitive_identifier",
        "pii",
        "internal_url",
        "security_document",
    ]
    return [blocker for blocker in ordered if blocker in MASK_ELIGIBLE_EXTERNAL_TRANSFER_BLOCKERS]


def _serialize_ai_security_data_protection(db: Session) -> AiSecurityDataProtectionResponse:
    settings = get_ai_security_data_protection_settings(db)
    runtime_settings = get_settings()
    privacy_filter_health = check_privacy_filter_health(settings=runtime_settings)
    return AiSecurityDataProtectionResponse(
        enforcement_enabled=(settings.enforcement_enabled if settings is not None else False),
        enforcement_disabled_reason=(
            settings.enforcement_disabled_reason if settings is not None else ""
        ),
        custom_block_terms=normalize_custom_block_terms(
            settings.custom_block_terms_json if settings is not None else []
        ),
        mandatory_blockers=_ai_security_mandatory_blockers(),
        hard_blockers=_ai_security_hard_blockers(),
        exception_eligible_blockers=_ai_security_exception_eligible_blockers(),
        mask_eligible_blockers=_ai_security_mask_eligible_blockers(),
        blocker_actions=ai_security_data_protection_blocker_actions(db),
        external_app_actions=ai_security_external_app_actions(db),
        privacy_filter_enabled=privacy_filter_health.enabled,
        privacy_filter_ready=privacy_filter_health.ready,
        privacy_filter_status=privacy_filter_health.status,
        privacy_filter_checkpoint=privacy_filter_health.checkpoint,
        privacy_filter_detail=privacy_filter_health.detail,
        privacy_filter_device=privacy_filter_health.device,
        updated_at=(
            settings.updated_at.isoformat()
            if settings is not None and settings.updated_at
            else None
        ),
        updated_by=settings.updated_by if settings is not None else None,
    )


def _ai_security_app_label(app_id: str) -> str | None:
    catalog_item = get_workspace_app_catalog_item(app_id)
    if catalog_item is not None:
        return catalog_item.title
    return None


def _ai_security_external_app_candidates() -> list[AiSecurityExternalAppCandidateResponse]:
    return [
        AiSecurityExternalAppCandidateResponse(
            app_id=profile.app_id,
            app_label=_ai_security_app_label(profile.app_id),
            task_kind=profile.task_kind,
            capability=profile.capability,
            provider=profile.provider,
            description=profile.profile_id,
        )
        for profile in iter_web_search_external_app_profiles()
    ]


def _ai_security_condition_options() -> AiSecurityConditionOptionsResponse:
    settings = get_settings()
    registry = get_ai_capability_registry()
    provider_values = [
        *get_allowed_external_llm_providers(settings),
        *allowed_external_providers(settings),
        *allowed_external_providers(settings, capability="search"),
    ]
    capability_values = [
        AI_SECURITY_LLM_CAPABILITY,
        *get_args(ExternalCapability),
        *(workload.task_kind for workload in registry.llm_workloads.values()),
        *(descriptor.name for descriptor in registry.descriptors.values()),
    ]
    return AiSecurityConditionOptionsResponse(
        apps=_ai_security_condition_option_items(
            (app.app_id, app.title) for app in iter_workspace_app_catalog()
        ),
        external_apps=_ai_security_condition_option_items(
            (item.app_id, item.app_label) for item in _ai_security_external_app_candidates()
        ),
        task_kinds=_ai_security_condition_option_items(
            (workload.task_kind, workload.description)
            for workload in registry.llm_workloads.values()
        ),
        capabilities=_ai_security_condition_option_items(capability_values),
        providers=_ai_security_condition_option_items(provider_values),
        content_origins=_ai_security_condition_option_items(known_content_origins()),
    )


def _ai_security_condition_option_items(
    values: Iterable[str | tuple[str, str | None]],
) -> list[AiSecurityConditionOptionResponse]:
    by_value: dict[str, AiSecurityConditionOptionResponse] = {}
    for raw_item in values:
        raw_value, label = raw_item if isinstance(raw_item, tuple) else (raw_item, None)
        value = str(raw_value or "").strip()
        if not value or value in by_value:
            continue
        by_value[value] = AiSecurityConditionOptionResponse(
            value=value,
            label=(label or None),
        )
    return [by_value[value] for value in sorted(by_value)]


def _ai_security_scope_task_kinds(
    task_kind: str | None,
    task_kinds_json: object,
) -> list[str]:
    task_kinds = normalize_ai_security_task_kinds(task_kinds_json)
    if not task_kinds and task_kind:
        task_kinds = normalize_ai_security_task_kinds([task_kind])
    return task_kinds


def _serialize_ai_security_rules(db: Session) -> list[AiSecurityPolicyRuleResponse]:
    rules = db.scalars(
        select(AiSecurityPolicyRule).order_by(
            AiSecurityPolicyRule.enabled.desc(),
            AiSecurityPolicyRule.updated_at.desc(),
            AiSecurityPolicyRule.id.desc(),
        )
    ).all()
    labels = _ai_security_rule_label_maps(db, rules)
    return [_serialize_ai_security_rule(rule, labels) for rule in rules]


def _serialize_ai_security_exceptions(
    db: Session,
) -> list[AiSecurityExternalTransferExceptionResponse]:
    exceptions = db.scalars(
        select(AiSecurityExternalTransferException).order_by(
            AiSecurityExternalTransferException.enabled.desc(),
            AiSecurityExternalTransferException.updated_at.desc(),
            AiSecurityExternalTransferException.id.desc(),
        )
    ).all()
    labels = _ai_security_exception_label_maps(db, exceptions)
    return [_serialize_ai_security_exception(exception, labels) for exception in exceptions]


def _serialize_ai_security_rule(
    rule: AiSecurityPolicyRule,
    labels: dict[str, dict[str, str]],
) -> AiSecurityPolicyRuleResponse:
    task_kinds = _ai_security_scope_task_kinds(rule.task_kind, rule.task_kinds_json)
    return AiSecurityPolicyRuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        enabled=rule.enabled,
        user_id=rule.user_id,
        user_name=labels["users"].get(rule.user_id or ""),
        workspace_id=rule.workspace_id,
        workspace_name=labels["workspaces"].get(rule.workspace_id or ""),
        app_id=rule.app_id,
        task_kind=task_kinds[0] if len(task_kinds) == 1 else None,
        task_kinds=task_kinds,
        capability=rule.capability,
        provider=rule.provider,
        effect=normalize_ai_security_effect(rule.effect),
        custom_block_terms=normalize_custom_block_terms(rule.custom_block_terms_json),
        created_at=rule.created_at.isoformat(),
        updated_at=rule.updated_at.isoformat(),
    )


def _serialize_ai_security_exception(
    exception: AiSecurityExternalTransferException,
    labels: dict[str, dict[str, str]],
) -> AiSecurityExternalTransferExceptionResponse:
    task_kinds = _ai_security_scope_task_kinds(
        exception.task_kind,
        exception.task_kinds_json,
    )
    return AiSecurityExternalTransferExceptionResponse(
        id=exception.id,
        name=exception.name,
        description=exception.description,
        enabled=exception.enabled,
        user_id=exception.user_id,
        user_name=labels["users"].get(exception.user_id or ""),
        workspace_id=exception.workspace_id,
        workspace_name=labels["workspaces"].get(exception.workspace_id or ""),
        app_id=exception.app_id,
        task_kind=task_kinds[0] if len(task_kinds) == 1 else None,
        task_kinds=task_kinds,
        capability=exception.capability,
        provider=exception.provider,
        allowed_blocker_types=normalize_external_transfer_blockers(
            exception.allowed_blocker_types_json
        ),
        reason=exception.reason,
        expires_at=exception.expires_at.isoformat() if exception.expires_at else None,
        created_at=exception.created_at.isoformat(),
        updated_at=exception.updated_at.isoformat(),
    )


def _ai_security_rule_label_maps(
    db: Session,
    rules: list[AiSecurityPolicyRule],
) -> dict[str, dict[str, str]]:
    user_ids = {rule.user_id for rule in rules if rule.user_id}
    workspace_ids = {rule.workspace_id for rule in rules if rule.workspace_id}
    users = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all())
        if user_ids
        else {}
    )
    workspaces = (
        dict(
            db.execute(
                select(Workspace.id, Workspace.name).where(Workspace.id.in_(workspace_ids))
            ).all()
        )
        if workspace_ids
        else {}
    )
    return {"users": users, "workspaces": workspaces}


def _ai_security_exception_label_maps(
    db: Session,
    exceptions: list[AiSecurityExternalTransferException],
) -> dict[str, dict[str, str]]:
    user_ids = {item.user_id for item in exceptions if item.user_id}
    workspace_ids = {item.workspace_id for item in exceptions if item.workspace_id}
    users = (
        dict(db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))).all())
        if user_ids
        else {}
    )
    workspaces = (
        dict(
            db.execute(
                select(Workspace.id, Workspace.name).where(Workspace.id.in_(workspace_ids))
            ).all()
        )
        if workspace_ids
        else {}
    )
    return {"users": users, "workspaces": workspaces}


def _validate_ai_security_rule_references(
    db: Session,
    payload: AiSecurityPolicyRuleUpsertRequest | AiSecurityExternalTransferExceptionUpsertRequest,
) -> None:
    if payload.user_id and db.scalar(select(User.id).where(User.id == payload.user_id)) is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    if (
        payload.workspace_id
        and db.scalar(select(Workspace.id).where(Workspace.id == payload.workspace_id)) is None
    ):
        raise localized_http_exception(status_code=404, code="workspace.not_found")


def _apply_ai_security_rule_payload(
    rule: AiSecurityPolicyRule,
    payload: AiSecurityPolicyRuleUpsertRequest,
    *,
    actor_user_id: str,
) -> None:
    rule.name = payload.name.strip()
    rule.description = payload.description.strip()
    rule.enabled = payload.enabled
    rule.user_id = payload.user_id
    rule.workspace_id = payload.workspace_id
    rule.app_id = payload.app_id
    rule.task_kinds_json = normalize_ai_security_task_kinds(payload.task_kinds)
    rule.task_kind = rule.task_kinds_json[0] if len(rule.task_kinds_json) == 1 else None
    rule.capability = payload.capability
    rule.provider = payload.provider
    rule.effect = normalize_ai_security_effect(payload.effect)
    rule.custom_block_terms_json = normalize_custom_block_terms(payload.custom_block_terms)
    rule.updated_by = actor_user_id


def _apply_ai_security_exception_payload(
    exception: AiSecurityExternalTransferException,
    payload: AiSecurityExternalTransferExceptionUpsertRequest,
    *,
    actor_user_id: str,
) -> None:
    expires_at = payload.expires_at
    if expires_at is not None and expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(UTC).replace(tzinfo=None)
    exception.name = payload.name.strip()
    exception.description = payload.description.strip()
    exception.enabled = payload.enabled
    exception.user_id = payload.user_id
    exception.workspace_id = payload.workspace_id
    exception.app_id = payload.app_id
    exception.task_kinds_json = normalize_ai_security_task_kinds(payload.task_kinds)
    exception.task_kind = (
        exception.task_kinds_json[0] if len(exception.task_kinds_json) == 1 else None
    )
    exception.capability = payload.capability
    exception.provider = payload.provider
    exception.allowed_blocker_types_json = normalize_external_transfer_blockers(
        payload.allowed_blocker_types
    )
    exception.reason = payload.reason.strip()
    exception.expires_at = expires_at
    exception.updated_by = actor_user_id


def _ai_security_rule_audit_payload(rule: AiSecurityPolicyRule) -> dict[str, object]:
    return {
        "rule_id": rule.id,
        "enabled": rule.enabled,
        "effect": normalize_ai_security_effect(rule.effect),
        "user_id": rule.user_id,
        "workspace_id": rule.workspace_id,
        "app_id": rule.app_id,
        "task_kind": rule.task_kind,
        "task_kinds": _ai_security_scope_task_kinds(rule.task_kind, rule.task_kinds_json),
        "capability": rule.capability,
        "provider": rule.provider,
        "custom_block_term_count": len(normalize_custom_block_terms(rule.custom_block_terms_json)),
    }


def _ai_security_exception_audit_payload(
    exception: AiSecurityExternalTransferException,
) -> dict[str, object]:
    return {
        "exception_id": exception.id,
        "enabled": exception.enabled,
        "user_id": exception.user_id,
        "workspace_id": exception.workspace_id,
        "app_id": exception.app_id,
        "task_kind": exception.task_kind,
        "task_kinds": _ai_security_scope_task_kinds(
            exception.task_kind,
            exception.task_kinds_json,
        ),
        "capability": exception.capability,
        "provider": exception.provider,
        "allowed_blocker_types": normalize_external_transfer_blockers(
            exception.allowed_blocker_types_json
        ),
        "expires_at": exception.expires_at.isoformat() if exception.expires_at else None,
        "reason_length": len(exception.reason or ""),
    }


def _ai_security_audit_log_count_24h(db: Session) -> int:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    return (
        db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.created_at >= since,
                or_(
                    AuditLog.action == "llm_call",
                    AuditLog.action == "ai_external_call",
                    AuditLog.action.like("admin.ai_security%"),
                ),
            )
        )
        or 0
    )


@dataclass(frozen=True)
class AiSecurityAuditClassification:
    security_event: bool
    blocked: bool
    forced_local: bool
    masked: bool
    external_exception: bool
    hard_blocker: bool
    reason: str
    entity_types: tuple[str, ...]

    @property
    def intervention(self) -> bool:
        return self.blocked or self.forced_local


def _ai_security_runtime_audit_action_condition() -> Any:
    return or_(
        AuditLog.action == "llm_call",
        AuditLog.action == "ai_external_call",
    )


def _ai_security_audit_action_condition() -> Any:
    return or_(
        _ai_security_runtime_audit_action_condition(),
        AuditLog.action.like("admin.ai_security%"),
    )


def _audit_payload_dict(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _audit_payload_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _audit_payload_bool(payload: dict[str, object], key: str) -> bool:
    return payload.get(key) is True


def _audit_payload_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def _audit_payload_strings(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if isinstance(value, Iterable):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                normalized = item.strip()
                if normalized:
                    result.append(normalized)
        return tuple(result)
    return ()


def _ai_security_audit_reason(
    action: str,
    payload: dict[str, object],
    *,
    blocked: bool,
    forced_local: bool,
    masked: bool,
) -> str:
    ignored_reasons = {"", "no_matching_rule", AI_SECURITY_ENFORCEMENT_DISABLED_REASON}
    for key in (
        "policy_reason",
        "decision_reason",
        "ai_security_policy_reason",
        "reason_code",
        "reason",
    ):
        value = _audit_payload_string(payload, key)
        if value and value not in ignored_reasons:
            return value
    effect = _audit_payload_string(payload, "ai_security_policy_effect")
    if effect:
        return effect
    status_value = _audit_payload_string(payload, "status")
    if status_value:
        return status_value
    if masked:
        return "mask_applied"
    if blocked:
        return "blocked"
    if forced_local:
        return "forced_local"
    return action


def _ai_security_audit_entity_types(payload: dict[str, object]) -> tuple[str, ...]:
    values: set[str] = set()
    for key in (
        "blocked_entity_types",
        "hard_blocker_types",
        "external_transfer_blocker_types",
        "masked_entity_types",
        "removed_entity_types",
    ):
        values.update(_audit_payload_strings(payload, key))
    if _audit_payload_int(payload, "custom_block_term_count") > 0:
        values.add(CUSTOM_BLOCK_ENTITY_TYPE)
    return tuple(sorted(values))


def _classify_ai_security_audit_log(item: AuditLog) -> AiSecurityAuditClassification:
    payload = _audit_payload_dict(item.payload)
    security_event = item.action in {"llm_call", "ai_external_call"}
    if not security_event:
        return AiSecurityAuditClassification(
            security_event=False,
            blocked=False,
            forced_local=False,
            masked=False,
            external_exception=False,
            hard_blocker=False,
            reason=item.action,
            entity_types=(),
        )

    status_value = _audit_payload_string(payload, "status").lower()
    policy_effect = _audit_payload_string(payload, "ai_security_policy_effect").lower()
    policy_reason = _audit_payload_string(payload, "ai_security_policy_reason")
    policy_rule_id = _audit_payload_string(payload, "ai_security_policy_rule_id")
    entity_types = _ai_security_audit_entity_types(payload)
    hard_blocker_types = {item for item in entity_types if item in HARD_EXTERNAL_TRANSFER_BLOCKERS}
    custom_block_term_count = _audit_payload_int(payload, "custom_block_term_count")
    if custom_block_term_count > 0:
        hard_blocker_types.add(CUSTOM_BLOCK_ENTITY_TYPE)

    blocked = (
        status_value in {"blocked", "blocked_external", "blocked_by_pii", "denied"}
        or policy_effect in {"block_external", "deny"}
        or bool(hard_blocker_types)
    )
    data_protection_hit = bool(entity_types) or custom_block_term_count > 0
    scoped_policy_hit = bool(policy_rule_id and policy_reason != "no_matching_rule")
    forced_local = policy_effect == "local_only" or (
        _audit_payload_bool(payload, "forced_local") and (data_protection_hit or scoped_policy_hit)
    )
    masked = _audit_payload_bool(payload, "mask_applied") or bool(
        _audit_payload_strings(payload, "masked_entity_types")
    )
    external_exception = bool(
        _audit_payload_string(payload, "external_transfer_exception_id")
        or _audit_payload_string(payload, "external_transfer_exception_reason")
    )
    reason = _ai_security_audit_reason(
        item.action,
        payload,
        blocked=blocked,
        forced_local=forced_local,
        masked=masked,
    )
    return AiSecurityAuditClassification(
        security_event=True,
        blocked=blocked,
        forced_local=forced_local,
        masked=masked,
        external_exception=external_exception,
        hard_blocker=bool(hard_blocker_types),
        reason=reason,
        entity_types=entity_types,
    )


def _ai_security_blocked_or_forced_log(item: AuditLog) -> bool:
    classification = _classify_ai_security_audit_log(item)
    return classification.intervention


def _ai_security_breakdown_items(
    counts: Counter[str],
    *,
    limit: int = 10,
) -> list[AiSecurityMonitoringBreakdownItemResponse]:
    return [
        AiSecurityMonitoringBreakdownItemResponse(
            key=key,
            label=key,
            count=count,
        )
        for key, count in sorted(
            counts.items(),
            key=lambda item: (item[1], item[0]),
            reverse=True,
        )[:limit]
    ]


def _ai_security_detected_value_search_condition(query: str | None):
    normalized = (query or "").strip()
    if not normalized:
        return None
    pattern = f"%{normalized}%"
    return or_(
        AiSecurityDetectedValue.detector.ilike(pattern),
        AiSecurityDetectedValue.entity_type.ilike(pattern),
        AiSecurityDetectedValue.blocker_type.ilike(pattern),
        AiSecurityDetectedValue.detected_value.ilike(pattern),
        AiSecurityDetectedValue.value_hash.ilike(pattern),
    )


def _ai_security_detected_value_base_conditions(
    *,
    start_at: datetime,
    end_at: datetime,
    privacy_filter: bool,
    query: str | None = None,
) -> list[Any]:
    where_clauses: list[Any] = [
        _usage_range_condition(AiSecurityDetectedValue.created_at, start_at, end_at),
    ]
    if privacy_filter:
        where_clauses.append(AiSecurityDetectedValue.detector == "privacy_filter")
    else:
        where_clauses.extend(
            [
                AiSecurityDetectedValue.detected_value.is_not(None),
                AiSecurityDetectedValue.detector != "privacy_filter",
            ]
        )
    search_condition = _ai_security_detected_value_search_condition(query)
    if search_condition is not None:
        where_clauses.append(search_condition)
    return where_clauses


def _ai_security_detected_value_groups(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
    privacy_filter: bool,
    limit: int,
    offset: int = 0,
    query: str | None = None,
) -> AiSecurityDetectedValueGroupsResponse:
    occurrence_total = func.coalesce(
        func.sum(AiSecurityDetectedValue.occurrence_count),
        0,
    ).label("occurrence_count")
    event_total = func.count(AiSecurityDetectedValue.id).label("event_count")
    distinct_value_total = func.count(
        func.distinct(
            func.coalesce(
                AiSecurityDetectedValue.value_hash,
                AiSecurityDetectedValue.detected_value,
            )
        )
    ).label("distinct_value_count")
    latest_at = func.max(AiSecurityDetectedValue.created_at).label("latest_at")
    where_clauses = _ai_security_detected_value_base_conditions(
        start_at=start_at,
        end_at=end_at,
        privacy_filter=privacy_filter,
        query=query,
    )
    group_columns = (
        AiSecurityDetectedValue.detector,
        AiSecurityDetectedValue.entity_type,
        AiSecurityDetectedValue.blocker_type,
    )
    grouped = select(*group_columns).where(*where_clauses).group_by(*group_columns).subquery()
    total = int(db.scalar(select(func.count()).select_from(grouped)) or 0)
    rows = db.execute(
        select(
            *group_columns,
            occurrence_total,
            event_total,
            distinct_value_total,
            latest_at,
        )
        .where(*where_clauses)
        .group_by(*group_columns)
        .order_by(
            occurrence_total.desc(),
            event_total.desc(),
            latest_at.desc(),
            AiSecurityDetectedValue.entity_type,
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return AiSecurityDetectedValueGroupsResponse(
        items=[
            AiSecurityDetectedValueGroupResponse(
                detector=str(row.detector or ""),
                entity_type=str(row.entity_type or ""),
                blocker_type=str(row.blocker_type or ""),
                occurrence_count=int(row.occurrence_count or 0),
                event_count=int(row.event_count or 0),
                distinct_value_count=int(row.distinct_value_count or 0),
                latest_at=row.latest_at.isoformat()
                if isinstance(row.latest_at, datetime)
                else None,
                detail_available=(
                    str(row.detector or "") != "privacy_filter"
                    and int(row.distinct_value_count or 0) > 0
                ),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _ai_security_detected_value_details(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
    detector: str,
    entity_type: str,
    blocker_type: str,
    limit: int,
    offset: int = 0,
    query: str | None = None,
) -> AiSecurityDetectedValueDetailsResponse:
    occurrence_total = func.coalesce(
        func.sum(AiSecurityDetectedValue.occurrence_count),
        0,
    ).label("occurrence_count")
    event_total = func.count(AiSecurityDetectedValue.id).label("event_count")
    where_clauses = [
        _usage_range_condition(AiSecurityDetectedValue.created_at, start_at, end_at),
        AiSecurityDetectedValue.detector == detector,
        AiSecurityDetectedValue.entity_type == entity_type,
        AiSecurityDetectedValue.blocker_type == blocker_type,
        AiSecurityDetectedValue.detected_value.is_not(None),
        AiSecurityDetectedValue.detector != "privacy_filter",
    ]
    search_condition = _ai_security_detected_value_search_condition(query)
    if search_condition is not None:
        where_clauses.append(search_condition)
    group_columns = (
        AiSecurityDetectedValue.detector,
        AiSecurityDetectedValue.entity_type,
        AiSecurityDetectedValue.blocker_type,
        AiSecurityDetectedValue.detected_value,
        AiSecurityDetectedValue.value_hash,
    )
    grouped = select(*group_columns).where(*where_clauses).group_by(*group_columns).subquery()
    total = int(db.scalar(select(func.count()).select_from(grouped)) or 0)
    rows = db.execute(
        select(
            *group_columns,
            occurrence_total,
            event_total,
        )
        .where(*where_clauses)
        .group_by(*group_columns)
        .order_by(
            occurrence_total.desc(),
            event_total.desc(),
            AiSecurityDetectedValue.detected_value,
        )
        .offset(offset)
        .limit(limit)
    ).all()

    return AiSecurityDetectedValueDetailsResponse(
        items=[
            AiSecurityDetectedValueStatResponse(
                detector=str(row.detector or ""),
                entity_type=str(row.entity_type or ""),
                blocker_type=str(row.blocker_type or ""),
                detected_value=row.detected_value if isinstance(row.detected_value, str) else None,
                value_hash=row.value_hash if isinstance(row.value_hash, str) else None,
                occurrence_count=int(row.occurrence_count or 0),
                event_count=int(row.event_count or 0),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


def _ai_security_detected_value_stats(
    db: Session,
    *,
    start_at: datetime,
    end_at: datetime,
    privacy_filter: bool,
    limit: int,
) -> list[AiSecurityDetectedValueStatResponse]:
    occurrence_total = func.coalesce(
        func.sum(AiSecurityDetectedValue.occurrence_count),
        0,
    ).label("occurrence_count")
    event_total = func.count(AiSecurityDetectedValue.id).label("event_count")
    where_clauses = [
        _usage_range_condition(AiSecurityDetectedValue.created_at, start_at, end_at),
    ]
    if privacy_filter:
        where_clauses.append(AiSecurityDetectedValue.detector == "privacy_filter")
    else:
        where_clauses.extend(
            [
                AiSecurityDetectedValue.detected_value.is_not(None),
                AiSecurityDetectedValue.detector != "privacy_filter",
            ]
        )

    rows = db.execute(
        select(
            AiSecurityDetectedValue.detector,
            AiSecurityDetectedValue.entity_type,
            AiSecurityDetectedValue.blocker_type,
            AiSecurityDetectedValue.detected_value,
            AiSecurityDetectedValue.value_hash,
            occurrence_total,
            event_total,
        )
        .where(*where_clauses)
        .group_by(
            AiSecurityDetectedValue.detector,
            AiSecurityDetectedValue.entity_type,
            AiSecurityDetectedValue.blocker_type,
            AiSecurityDetectedValue.detected_value,
            AiSecurityDetectedValue.value_hash,
        )
        .order_by(occurrence_total.desc(), event_total.desc(), AiSecurityDetectedValue.entity_type)
        .limit(limit)
    ).all()

    return [
        AiSecurityDetectedValueStatResponse(
            detector=str(row.detector or ""),
            entity_type=str(row.entity_type or ""),
            blocker_type=str(row.blocker_type or ""),
            detected_value=row.detected_value if isinstance(row.detected_value, str) else None,
            value_hash=row.value_hash if isinstance(row.value_hash, str) else None,
            occurrence_count=int(row.occurrence_count or 0),
            event_count=int(row.event_count or 0),
        )
        for row in rows
    ]


def _build_ai_security_monitoring(
    db: Session,
    *,
    days: int | None,
    from_date: date | None,
    to_date: date | None,
    limit: int,
) -> AiSecurityMonitoringResponse:
    usage_range = _resolve_usage_date_range(
        days=days,
        from_date=from_date,
        to_date=to_date,
        max_days=MAX_AUDIT_LOG_RANGE_DAYS,
    )
    date_values = [
        usage_range.from_date + timedelta(days=offset) for offset in range(usage_range.period_days)
    ]
    trend_by_day = {
        value.isoformat(): {
            "blocked_count": 0,
            "forced_local_count": 0,
            "masked_count": 0,
        }
        for value in date_values
    }
    rows = db.scalars(
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .where(
            _usage_range_condition(
                AuditLog.created_at,
                usage_range.start_at,
                usage_range.end_at,
            ),
            _ai_security_runtime_audit_action_condition(),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    ).all()

    blocked_events: list[AuditLog] = []
    actor_ids: set[str] = set()
    reason_counts: Counter[str] = Counter()
    entity_counts: Counter[str] = Counter()
    user_counts: dict[str, dict[str, object]] = {}
    blocked_event_count = 0
    forced_local_count = 0
    masked_event_count = 0
    external_exception_count = 0
    hard_blocker_count = 0
    security_event_count = 0

    for row in rows:
        classification = _classify_ai_security_audit_log(row)
        if not classification.security_event:
            continue
        security_relevant = (
            classification.intervention
            or classification.masked
            or classification.external_exception
        )
        if not security_relevant:
            continue
        security_event_count += 1
        if row.actor_user_id:
            actor_ids.add(row.actor_user_id)
        if classification.blocked:
            blocked_event_count += 1
        if classification.forced_local:
            forced_local_count += 1
        if classification.masked:
            masked_event_count += 1
        if classification.external_exception:
            external_exception_count += 1
        if classification.hard_blocker:
            hard_blocker_count += 1

        day_key = _date_key(row.created_at)
        if day_key in trend_by_day:
            if classification.blocked:
                trend_by_day[day_key]["blocked_count"] += 1
            if classification.forced_local:
                trend_by_day[day_key]["forced_local_count"] += 1
            if classification.masked:
                trend_by_day[day_key]["masked_count"] += 1

        if row.actor_user_id:
            actor = row.actor
            current = user_counts.setdefault(
                row.actor_user_id,
                {
                    "user_id": row.actor_user_id,
                    "full_name": actor.full_name if actor else row.actor_user_id,
                    "email": actor.email if actor else "",
                    "blocked_count": 0,
                    "forced_local_count": 0,
                    "masked_count": 0,
                    "last_blocked_at": None,
                },
            )
            if classification.blocked:
                current["blocked_count"] = int(current["blocked_count"]) + 1
            if classification.forced_local:
                current["forced_local_count"] = int(current["forced_local_count"]) + 1
            if classification.masked:
                current["masked_count"] = int(current["masked_count"]) + 1
            last_blocked_at = current["last_blocked_at"]
            if not isinstance(last_blocked_at, datetime) or row.created_at > last_blocked_at:
                current["last_blocked_at"] = row.created_at

        if not classification.intervention:
            continue

        blocked_events.append(row)
        reason_counts[classification.reason] += 1
        if classification.entity_types:
            for entity_type in classification.entity_types:
                entity_counts[entity_type] += 1
        else:
            entity_counts["unknown"] += 1

    user_items = []
    for item in user_counts.values():
        blocked_count = int(item["blocked_count"])
        forced_count = int(item["forced_local_count"])
        masked_count = int(item["masked_count"])
        last_blocked_at = item["last_blocked_at"]
        user_items.append(
            AiSecurityMonitoringUserItemResponse(
                user_id=str(item["user_id"]),
                full_name=str(item["full_name"]),
                email=str(item["email"]),
                blocked_count=blocked_count,
                forced_local_count=forced_count,
                masked_count=masked_count,
                total_count=blocked_count + forced_count + masked_count,
                last_blocked_at=(
                    last_blocked_at.isoformat() if isinstance(last_blocked_at, datetime) else None
                ),
            )
        )
    user_items.sort(
        key=lambda item: (
            item.total_count,
            item.blocked_count,
            item.forced_local_count,
            item.last_blocked_at or "",
            item.full_name,
        ),
        reverse=True,
    )

    return AiSecurityMonitoringResponse(
        period_days=usage_range.period_days,
        from_date=usage_range.from_date,
        to_date=usage_range.to_date,
        generated_at=usage_range.generated_at.isoformat(),
        totals=AiSecurityMonitoringTotalsResponse(
            security_event_count=security_event_count,
            blocked_event_count=blocked_event_count,
            forced_local_count=forced_local_count,
            masked_event_count=masked_event_count,
            external_exception_count=external_exception_count,
            hard_blocker_count=hard_blocker_count,
            unique_actor_count=len(actor_ids),
        ),
        daily_trends=[
            AiSecurityMonitoringTrendPointResponse(
                date=day,
                blocked_count=values["blocked_count"],
                forced_local_count=values["forced_local_count"],
                masked_count=values["masked_count"],
            )
            for day, values in trend_by_day.items()
        ],
        blocked_by_user=user_items[:limit],
        blocked_by_reason=_ai_security_breakdown_items(reason_counts),
        blocked_by_entity_type=_ai_security_breakdown_items(entity_counts),
        detected_value_groups=_ai_security_detected_value_groups(
            db,
            start_at=usage_range.start_at,
            end_at=usage_range.end_at,
            privacy_filter=False,
            limit=limit,
        ).items,
        privacy_filter_groups=_ai_security_detected_value_groups(
            db,
            start_at=usage_range.start_at,
            end_at=usage_range.end_at,
            privacy_filter=True,
            limit=limit,
        ).items,
        detected_value_rankings=_ai_security_detected_value_stats(
            db,
            start_at=usage_range.start_at,
            end_at=usage_range.end_at,
            privacy_filter=False,
            limit=limit,
        ),
        privacy_filter_rankings=_ai_security_detected_value_stats(
            db,
            start_at=usage_range.start_at,
            end_at=usage_range.end_at,
            privacy_filter=True,
            limit=limit,
        ),
        blocked_events=[
            _serialize_audit_log_item(item) for item in blocked_events[: min(limit, 100)]
        ],
    )


def _ai_security_route_action(
    *,
    policy_effect: AiSecurityPolicyEffect,
    safety_allow_external: bool,
    custom_block_term_count: int,
    external_transfer_exception_allowed: bool = False,
) -> Literal["unchanged", "blocked", "audit_only", "external_exception"]:
    if external_transfer_exception_allowed:
        return "external_exception"
    if not safety_allow_external:
        return "blocked"
    if custom_block_term_count > 0:
        return "blocked"
    if policy_effect == "block_external":
        return "blocked"
    if policy_effect == "audit_only":
        return "audit_only"
    return "unchanged"


def _ai_security_global_action_for_blockers(
    db: Session,
    blocker_types: tuple[str, ...],
) -> AiSecurityDataProtectionAction | None:
    if not blocker_types:
        return None
    blocker_actions = ai_security_data_protection_blocker_actions(db)
    actionable_blockers = [blocker for blocker in blocker_types if blocker in blocker_actions]
    if not actionable_blockers:
        return None
    if len(actionable_blockers) != len(blocker_types):
        return None
    if all(blocker_actions[blocker] == "mask_and_send" for blocker in actionable_blockers):
        return "mask_and_send"
    return "block"


@dataclass(frozen=True)
class UsageDateRange:
    from_date: date
    to_date: date
    start_at: datetime
    end_at: datetime
    generated_at: datetime
    period_days: int


def _usage_local_datetime(value: datetime) -> datetime:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(USAGE_DASHBOARD_TIME_ZONE)


def _usage_local_day_start_utc(value: date) -> datetime:
    local_start = datetime.combine(value, time.min, tzinfo=USAGE_DASHBOARD_TIME_ZONE)
    return local_start.astimezone(UTC).replace(tzinfo=None)


def _resolve_usage_date_range(
    *,
    days: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    max_days: int,
) -> UsageDateRange:
    generated_at = datetime.now(UTC).replace(tzinfo=None)
    today = _usage_local_datetime(generated_at).date()

    if from_date is None and to_date is None:
        resolved_days = max(days or 7, 1)
        resolved_to = today
        resolved_from = resolved_to - timedelta(days=resolved_days - 1)
    else:
        resolved_to = to_date or today
        if resolved_to > today:
            raise localized_http_exception(
                status_code=422,
                code="admin.usage_to_date_future",
            )
        if from_date is None:
            resolved_days = max(days or 1, 1)
            resolved_from = resolved_to - timedelta(days=resolved_days - 1)
        else:
            resolved_from = from_date

    if resolved_from > resolved_to:
        raise localized_http_exception(
            status_code=422,
            code="admin.usage_date_range_invalid",
        )

    period_days = (resolved_to - resolved_from).days + 1
    if period_days > max_days:
        raise localized_http_exception(
            status_code=422,
            code="admin.usage_date_range_too_long",
            max_days=max_days,
        )

    end_at = (
        generated_at
        if resolved_to == today
        else _usage_local_day_start_utc(resolved_to + timedelta(days=1))
    )
    return UsageDateRange(
        from_date=resolved_from,
        to_date=resolved_to,
        start_at=_usage_local_day_start_utc(resolved_from),
        end_at=end_at,
        generated_at=generated_at,
        period_days=period_days,
    )


def _usage_window(days: int) -> tuple[datetime, datetime]:
    window = _resolve_usage_date_range(
        days=days,
        max_days=MAX_AUDIT_LOG_RANGE_DAYS,
    )
    return window.start_at, window.end_at


def _usage_range_condition(column: Any, since: datetime, until: datetime) -> Any:
    return and_(column >= since, column < until)


def _usage_excluded_user_ids(db: Session) -> set[str]:
    from open_work_hub_api.domains.usage.models import UsageExcludedUser

    return set(db.scalars(select(UsageExcludedUser.user_id)).all())


@dataclass(frozen=True)
class UsageTargetScope:
    configured: bool
    explicit_user_ids: set[str]
    user_ids: set[str] | None


def _usage_target_scope(db: Session) -> UsageTargetScope:
    from open_work_hub_api.domains.usage.models import UsageTargetUser

    explicit_user_ids = set(db.scalars(select(UsageTargetUser.user_id)).all())
    if not explicit_user_ids:
        return UsageTargetScope(
            configured=False,
            explicit_user_ids=set(),
            user_ids=None,
        )

    return UsageTargetScope(
        configured=True,
        explicit_user_ids=explicit_user_ids,
        user_ids=set(explicit_user_ids),
    )


def _serialize_usage_target_scope(
    scope: UsageTargetScope, user_count: int
) -> AdminUsageTargetScopeResponse:
    return AdminUsageTargetScopeResponse(
        configured=scope.configured,
        user_count=user_count,
        explicit_user_count=len(scope.explicit_user_ids),
    )


def _serialize_usage_excluded_users(
    db: Session,
) -> list[AdminUsageExcludedUserItemResponse]:
    from open_work_hub_api.domains.usage.models import UsageExcludedUser

    rows = db.execute(
        select(User, UsageExcludedUser)
        .join(UsageExcludedUser, UsageExcludedUser.user_id == User.id)
        .order_by(User.full_name.asc(), User.email.asc())
    ).all()
    return [
        AdminUsageExcludedUserItemResponse(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            excluded_at=excluded.created_at.isoformat(),
        )
        for user, excluded in rows
    ]


def _serialize_usage_targets(db: Session) -> AdminUsageTargetsResponse:
    from open_work_hub_api.domains.usage.models import UsageTargetUser

    user_rows = db.execute(
        select(User, UsageTargetUser)
        .join(UsageTargetUser, UsageTargetUser.user_id == User.id)
        .order_by(User.full_name.asc(), User.email.asc())
    ).all()
    scope = _usage_target_scope(db)
    return AdminUsageTargetsResponse(
        users=[
            AdminUsageTargetUserItemResponse(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,
                targeted_at=target.created_at.isoformat(),
            )
            for user, target in user_rows
        ],
        resolved_user_count=len(scope.user_ids or set()),
    )


def _count_by_user(
    db: Session,
    model: type[Any],
    user_column: Any,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    created_column: Any | None = None,
    extra_conditions: list[Any] | None = None,
    excluded_user_ids: set[str] | None = None,
    included_user_ids: set[str] | None = None,
) -> dict[str, int]:
    conditions = [user_column.is_not(None)]
    if included_user_ids is not None:
        conditions.append(user_column.in_(included_user_ids))
    if excluded_user_ids:
        conditions.append(~user_column.in_(excluded_user_ids))
    if since is not None and created_column is not None:
        conditions.append(created_column >= since)
    if until is not None and created_column is not None:
        conditions.append(created_column < until)
    conditions.extend(extra_conditions or [])
    rows = db.execute(
        select(user_column, func.count())
        .select_from(model)
        .where(*conditions)
        .group_by(user_column)
    ).all()
    return {str(user_id): int(count) for user_id, count in rows if user_id is not None}


def _usage_count_by_user(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    event_type: str | None = None,
    content_kind: str | None = None,
    excluded_user_ids: set[str] | None = None,
    included_user_ids: set[str] | None = None,
) -> dict[str, int]:
    from open_work_hub_api.domains.usage.models import UsageEvent

    conditions = [
        _usage_range_condition(UsageEvent.occurred_at, since, until),
        UsageEvent.actor_user_id.is_not(None),
    ]
    if included_user_ids is not None:
        conditions.append(UsageEvent.actor_user_id.in_(included_user_ids))
    if excluded_user_ids:
        conditions.append(~UsageEvent.actor_user_id.in_(excluded_user_ids))
    if event_type is not None:
        conditions.append(UsageEvent.event_type == event_type)
    if content_kind is not None:
        conditions.append(UsageEvent.content_kind == content_kind)
    rows = db.execute(
        select(UsageEvent.actor_user_id, func.coalesce(func.sum(UsageEvent.count), 0))
        .where(*conditions)
        .group_by(UsageEvent.actor_user_id)
    ).all()
    return {str(user_id): int(count) for user_id, count in rows if user_id is not None}


def _usage_breakdown_counts(
    db: Session,
    column: Any,
    *,
    since: datetime,
    until: datetime,
    event_type: str | None = None,
    exclude_empty: bool = False,
    excluded_user_ids: set[str] | None = None,
    included_user_ids: set[str] | None = None,
) -> dict[str, dict[str, int]]:
    from open_work_hub_api.domains.usage.models import UsageEvent

    conditions = [_usage_range_condition(UsageEvent.occurred_at, since, until)]
    if included_user_ids is not None:
        conditions.append(UsageEvent.actor_user_id.in_(included_user_ids))
    if excluded_user_ids:
        conditions.append(~UsageEvent.actor_user_id.in_(excluded_user_ids))
    if event_type is not None:
        conditions.append(UsageEvent.event_type == event_type)
    if exclude_empty:
        conditions.append(column.is_not(None))
    rows = db.execute(
        select(column, func.coalesce(func.sum(UsageEvent.count), 0))
        .select_from(UsageEvent)
        .where(*conditions)
        .group_by(column)
    ).all()
    return {str(key or "unknown"): {"count": int(count), "total_tokens": 0} for key, count in rows}


def _extend_user_time_rows(
    rows: list[tuple[str, datetime]],
    db: Session,
    model: type[Any],
    user_column: Any,
    time_column: Any,
    *,
    since: datetime,
    until: datetime,
    excluded_user_ids: set[str],
    included_user_ids: set[str] | None = None,
    extra_conditions: list[Any] | None = None,
) -> None:
    conditions = [
        user_column.is_not(None),
        _usage_range_condition(time_column, since, until),
    ]
    if included_user_ids is not None:
        conditions.append(user_column.in_(included_user_ids))
    if excluded_user_ids:
        conditions.append(~user_column.in_(excluded_user_ids))
    conditions.extend(extra_conditions or [])
    for user_id, occurred_at in db.execute(
        select(user_column, time_column).select_from(model).where(*conditions)
    ).all():
        if user_id is not None and occurred_at is not None:
            rows.append((str(user_id), occurred_at))


def _period_activity_rows(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    excluded_user_ids: set[str],
    included_user_ids: set[str] | None = None,
) -> list[tuple[str, datetime]]:
    from open_work_hub_api.domains.docs.models import NativeDoc
    from open_work_hub_api.domains.meeting.models import Meeting
    from open_work_hub_api.domains.pms.models import (
        Attachment,
        Task,
        TaskActivityLog,
        TaskComment,
        TaskList,
    )
    from open_work_hub_api.domains.usage.models import UsageEvent
    from open_work_hub_api.domains.whiteboard.models import Whiteboard

    rows: list[tuple[str, datetime]] = []
    activity_sources: list[tuple[type[Any], Any, Any, list[Any]]] = [
        (AuthSession, AuthSession.user_id, AuthSession.created_at, []),
        (AuthSession, AuthSession.user_id, AuthSession.last_seen_at, []),
        (UsageEvent, UsageEvent.actor_user_id, UsageEvent.occurred_at, []),
        (AuditLog, AuditLog.actor_user_id, AuditLog.created_at, []),
        (NativeDoc, NativeDoc.owner_id, NativeDoc.created_at, [NativeDoc.trashed_at.is_(None)]),
        (
            Whiteboard,
            Whiteboard.owner_id,
            Whiteboard.created_at,
            [Whiteboard.trashed_at.is_(None)],
        ),
        (Meeting, Meeting.organizer_id, Meeting.created_at, []),
        (TaskList, TaskList.created_by_id, TaskList.created_at, [TaskList.archived.is_(False)]),
        (Task, Task.reporter_id, Task.created_at, [Task.archived.is_(False)]),
        (TaskComment, TaskComment.author_id, TaskComment.created_at, []),
        (TaskActivityLog, TaskActivityLog.actor_id, TaskActivityLog.created_at, []),
        (Attachment, Attachment.uploaded_by_id, Attachment.created_at, []),
    ]
    for model, user_column, time_column, extra_conditions in activity_sources:
        _extend_user_time_rows(
            rows,
            db,
            model,
            user_column,
            time_column,
            since=since,
            until=until,
            excluded_user_ids=excluded_user_ids,
            included_user_ids=included_user_ids,
            extra_conditions=extra_conditions,
        )
    return rows


def _date_key(value: date | datetime) -> str:
    if isinstance(value, datetime):
        return _usage_local_datetime(value).date().isoformat()
    return value.isoformat()


def _build_daily_trends(
    db: Session,
    *,
    from_date: date,
    to_date: date,
    since: datetime,
    until: datetime,
    excluded_user_ids: set[str],
    included_user_ids: set[str] | None = None,
) -> list[AdminUsageTrendPointResponse]:
    period_days = (to_date - from_date).days + 1
    date_values = [from_date + timedelta(days=offset) for offset in range(period_days)]
    date_keys = [_date_key(value) for value in date_values]
    visitor_by_day: dict[str, set[str]] = {key: set() for key in date_keys}
    active_by_day: dict[str, set[str]] = {key: set() for key in date_keys}

    session_conditions = [
        AuthSession.user_id.is_not(None),
        or_(
            _usage_range_condition(AuthSession.created_at, since, until),
            _usage_range_condition(AuthSession.last_seen_at, since, until),
        ),
    ]
    if included_user_ids is not None:
        session_conditions.append(AuthSession.user_id.in_(included_user_ids))
    if excluded_user_ids:
        session_conditions.append(~AuthSession.user_id.in_(excluded_user_ids))
    session_rows = db.execute(
        select(AuthSession.user_id, AuthSession.created_at, AuthSession.last_seen_at).where(
            *session_conditions
        )
    ).all()
    for user_id, created_at, last_seen_at in session_rows:
        if user_id is None:
            continue
        user_key = str(user_id)
        if created_at is not None and since <= created_at < until:
            key = _date_key(created_at)
            if key in visitor_by_day:
                visitor_by_day[key].add(user_key)
                active_by_day[key].add(user_key)
        if last_seen_at is not None and since <= last_seen_at < until:
            key = _date_key(last_seen_at)
            if key in visitor_by_day:
                visitor_by_day[key].add(user_key)
                active_by_day[key].add(user_key)

    for user_id, occurred_at in _period_activity_rows(
        db,
        since=since,
        until=until,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=included_user_ids,
    ):
        key = _date_key(occurred_at)
        if key in active_by_day:
            active_by_day[key].add(str(user_id))

    return [
        AdminUsageTrendPointResponse(
            date=key,
            visitor_count=len(visitor_by_day[key]),
            active_user_count=len(active_by_day[key]),
        )
        for key in date_keys
    ]


def _build_hourly_access(
    db: Session,
    *,
    period_days: int,
    since: datetime,
    until: datetime,
    excluded_user_ids: set[str],
    included_user_ids: set[str] | None = None,
) -> list[AdminUsageHourlyPointResponse]:
    buckets: dict[int, dict[str, object]] = {
        hour: {"login_count": 0, "visitor_ids": set(), "daily_visitor_ids": {}, "daily_logins": {}}
        for hour in range(24)
    }
    conditions = [
        AuthSession.user_id.is_not(None),
        or_(
            _usage_range_condition(AuthSession.created_at, since, until),
            _usage_range_condition(AuthSession.last_seen_at, since, until),
        ),
    ]
    if included_user_ids is not None:
        conditions.append(AuthSession.user_id.in_(included_user_ids))
    if excluded_user_ids:
        conditions.append(~AuthSession.user_id.in_(excluded_user_ids))
    rows = db.execute(
        select(AuthSession.user_id, AuthSession.created_at, AuthSession.last_seen_at).where(
            *conditions
        )
    ).all()
    for user_id, created_at, last_seen_at in rows:
        user_key = str(user_id)
        if created_at is not None and since <= created_at < until:
            created_local = _usage_local_datetime(created_at)
            created_bucket = buckets[created_local.hour]
            created_bucket["login_count"] = int(created_bucket["login_count"]) + 1
            daily_logins = created_bucket["daily_logins"]
            if isinstance(daily_logins, dict):
                day_key = created_local.date().isoformat()
                daily_logins[day_key] = int(daily_logins.get(day_key, 0)) + 1
            visitor_ids = created_bucket["visitor_ids"]
            if isinstance(visitor_ids, set):
                visitor_ids.add(user_key)
            daily_visitor_ids = created_bucket["daily_visitor_ids"]
            if isinstance(daily_visitor_ids, dict):
                day_key = created_local.date().isoformat()
                day_visitors = daily_visitor_ids.setdefault(day_key, set())
                if isinstance(day_visitors, set):
                    day_visitors.add(user_key)
        if last_seen_at is not None and since <= last_seen_at < until:
            seen_local = _usage_local_datetime(last_seen_at)
            seen_bucket = buckets[seen_local.hour]
            visitor_ids = seen_bucket["visitor_ids"]
            if isinstance(visitor_ids, set):
                visitor_ids.add(user_key)
            daily_visitor_ids = seen_bucket["daily_visitor_ids"]
            if isinstance(daily_visitor_ids, dict):
                day_key = seen_local.date().isoformat()
                day_visitors = daily_visitor_ids.setdefault(day_key, set())
                if isinstance(day_visitors, set):
                    day_visitors.add(user_key)

    return [
        AdminUsageHourlyPointResponse(
            hour=hour,
            login_count=int(bucket["login_count"]),
            visitor_count=len(bucket["visitor_ids"])
            if isinstance(bucket["visitor_ids"], set)
            else 0,
            average_login_count=round(
                sum(bucket["daily_logins"].values()) / max(1, period_days),
                1,
            )
            if isinstance(bucket["daily_logins"], dict)
            else 0,
            average_visitor_count=round(
                sum(len(value) for value in bucket["daily_visitor_ids"].values())
                / max(1, period_days),
                1,
            )
            if isinstance(bucket["daily_visitor_ids"], dict)
            else 0,
        )
        for hour, bucket in buckets.items()
    ]


def _build_token_rankings(
    user_items: list[AdminUsageUserItemResponse],
    *,
    limit: int = 10,
) -> list[AdminUsageTokenRankItemResponse]:
    return [
        AdminUsageTokenRankItemResponse(
            user_id=item.user_id,
            full_name=item.full_name,
            email=item.email,
            llm_call_count=item.llm_call_count,
            llm_total_tokens=item.llm_total_tokens,
        )
        for item in sorted(
            [item for item in user_items if item.llm_total_tokens > 0],
            key=lambda item: (item.llm_total_tokens, item.llm_call_count, item.full_name.lower()),
            reverse=True,
        )[:limit]
    ]


def _build_pms_summary(
    db: Session,
    *,
    since: datetime,
    until: datetime,
    excluded_user_ids: set[str],
    included_user_ids: set[str] | None = None,
) -> AdminUsagePmsSummaryResponse:
    from open_work_hub_api.domains.pms.models import (
        Attachment,
        Task,
        TaskActivityLog,
        TaskComment,
        TaskList,
    )

    project_conditions = [TaskList.archived.is_(False)]
    if included_user_ids is not None:
        project_conditions.append(TaskList.created_by_id.in_(included_user_ids))
    elif excluded_user_ids:
        project_conditions.append(~TaskList.created_by_id.in_(excluded_user_ids))
    project_count = int(db.scalar(select(func.count(TaskList.id)).where(*project_conditions)) or 0)

    stakeholder_ids = set(
        db.scalars(
            select(TaskList.created_by_id).where(
                TaskList.archived.is_(False),
                TaskList.created_by_id.is_not(None),
            )
        )
    )
    task_user_rows = db.execute(
        select(Task.reporter_id, Task.assignee_id)
        .join(TaskList, TaskList.id == Task.list_id)
        .where(Task.archived.is_(False), TaskList.archived.is_(False))
    ).all()
    for reporter_id, assignee_id in task_user_rows:
        if reporter_id is not None:
            stakeholder_ids.add(str(reporter_id))
        if assignee_id is not None:
            stakeholder_ids.add(str(assignee_id))
    stakeholder_ids.update(
        db.scalars(
            select(Attachment.uploaded_by_id)
            .join(Task, Task.id == Attachment.task_id)
            .join(TaskList, TaskList.id == Task.list_id)
            .where(
                Task.archived.is_(False),
                TaskList.archived.is_(False),
                Attachment.uploaded_by_id.is_not(None),
            )
        )
    )
    stakeholder_ids.update(
        db.scalars(
            select(TeamMember.user_id)
            .join(Team, Team.id == TeamMember.team_id)
            .join(TaskList, TaskList.team_id == Team.id)
            .where(Team.active.is_(True), TaskList.archived.is_(False))
        )
    )
    stakeholder_ids = {str(user_id) for user_id in stakeholder_ids if user_id is not None}
    if included_user_ids is not None:
        stakeholder_ids.intersection_update(included_user_ids)
    stakeholder_ids.difference_update(excluded_user_ids)

    attachment_conditions = [Task.archived.is_(False), TaskList.archived.is_(False)]
    if included_user_ids is not None:
        attachment_conditions.append(Attachment.uploaded_by_id.in_(included_user_ids))
    elif excluded_user_ids:
        attachment_conditions.append(~Attachment.uploaded_by_id.in_(excluded_user_ids))
    attachment_count, attachment_total_bytes = db.execute(
        select(
            func.count(Attachment.id),
            func.coalesce(func.sum(Attachment.size_bytes), 0),
        )
        .join(Task, Task.id == Attachment.task_id)
        .join(TaskList, TaskList.id == Task.list_id)
        .where(*attachment_conditions)
    ).one()

    activity_conditions = [
        _usage_range_condition(TaskActivityLog.created_at, since, until),
        TaskActivityLog.actor_id.is_not(None),
    ]
    if included_user_ids is not None:
        activity_conditions.append(TaskActivityLog.actor_id.in_(included_user_ids))
    elif excluded_user_ids:
        activity_conditions.append(~TaskActivityLog.actor_id.in_(excluded_user_ids))
    task_activity_rows = db.execute(
        select(TaskActivityLog.actor_id, func.count(TaskActivityLog.id))
        .where(*activity_conditions)
        .group_by(TaskActivityLog.actor_id)
    ).all()
    pms_active_user_ids = {str(user_id) for user_id, _count in task_activity_rows if user_id}
    task_activity_count = sum(int(count) for _user_id, count in task_activity_rows)

    comment_conditions = [
        _usage_range_condition(TaskComment.created_at, since, until),
        TaskComment.author_id.is_not(None),
    ]
    if included_user_ids is not None:
        comment_conditions.append(TaskComment.author_id.in_(included_user_ids))
    elif excluded_user_ids:
        comment_conditions.append(~TaskComment.author_id.in_(excluded_user_ids))
    task_comment_rows = db.execute(
        select(TaskComment.author_id, func.count(TaskComment.id))
        .where(*comment_conditions)
        .group_by(TaskComment.author_id)
    ).all()
    pms_active_user_ids.update(str(user_id) for user_id, _count in task_comment_rows if user_id)
    task_comment_count = sum(int(count) for _user_id, count in task_comment_rows)

    attachment_added_conditions = [
        _usage_range_condition(Attachment.created_at, since, until),
        Attachment.uploaded_by_id.is_not(None),
    ]
    if included_user_ids is not None:
        attachment_added_conditions.append(Attachment.uploaded_by_id.in_(included_user_ids))
    elif excluded_user_ids:
        attachment_added_conditions.append(~Attachment.uploaded_by_id.in_(excluded_user_ids))
    attachment_added_count = int(
        db.scalar(select(func.count(Attachment.id)).where(*attachment_added_conditions)) or 0
    )

    return AdminUsagePmsSummaryResponse(
        project_count=project_count,
        stakeholder_count=len(stakeholder_ids),
        attachment_count=int(attachment_count),
        attachment_total_bytes=int(attachment_total_bytes),
        active_user_count=len(pms_active_user_ids),
        task_activity_count=task_activity_count,
        task_comment_count=task_comment_count,
        attachment_added_count=attachment_added_count,
    )


def _build_ai_team_summary(
    db: Session,
    *,
    since: datetime,
    until: datetime,
) -> AdminUsageAiTeamSummaryResponse:
    from open_work_hub_api.domains.community.models import (
        CommunityChannel,
        CommunityComment,
        CommunityPost,
    )
    from open_work_hub_api.domains.community.service import DEFAULT_CHANNEL_KEY
    from open_work_hub_api.domains.ai.runtime_status import inspect_registered_llm_runtime

    health = inspect_registered_llm_runtime(db, probe="configured").pools.public_dict(
        locale="ko-KR",
        include_base_url=False,
    )
    raw_connections: list[dict[str, object]] = []
    local_health = health.get("local")
    if isinstance(local_health, dict):
        raw_connections.append(local_health)
    external_health = health.get("external")
    if isinstance(external_health, dict):
        raw_connections.append(external_health)
    external_providers = health.get("external_providers")
    if isinstance(external_providers, list):
        raw_connections.extend(item for item in external_providers if isinstance(item, dict))

    connections: list[AdminUsageAiConnectionItemResponse] = []
    seen_connections: set[tuple[str, str, str]] = set()
    for item in raw_connections:
        pool = str(item.get("pool") or "unknown")
        provider = str(item.get("provider") or "unknown")
        model = str(item.get("model") or "")
        connection_key = (pool, provider, model)
        if connection_key in seen_connections:
            continue
        seen_connections.add(connection_key)
        connections.append(
            AdminUsageAiConnectionItemResponse(
                pool=pool,
                provider=provider,
                status=str(item.get("status") or "unknown"),
                ready=bool(item.get("ready")),
                model=model,
                canonical_model=str(item.get("canonical_model") or model),
                detail=str(item["detail"]) if item.get("detail") else None,
            )
        )

    suggestions_channel = db.scalar(
        select(CommunityChannel).where(CommunityChannel.key == DEFAULT_CHANNEL_KEY)
    )
    suggestion_post_ids: set[str] = set()
    if suggestions_channel is not None:
        suggestion_post_ids = set(
            db.scalars(
                select(CommunityPost.id).where(
                    CommunityPost.channel_id == suggestions_channel.id,
                    _usage_range_condition(CommunityPost.created_at, since, until),
                )
            )
        )
    answered_post_ids: set[str] = set()
    if suggestion_post_ids:
        answered_post_ids = set(
            db.scalars(
                select(CommunityComment.post_id).where(
                    CommunityComment.post_id.in_(suggestion_post_ids),
                    CommunityComment.is_deleted.is_(False),
                )
            )
        )

    return AdminUsageAiTeamSummaryResponse(
        connections=connections,
        suggestion_count=len(suggestion_post_ids),
        unanswered_suggestion_count=len(suggestion_post_ids - answered_post_ids),
    )


def _sum_counts(*items: dict[str, int]) -> int:
    return sum(sum(item.values()) for item in items)


def _safe_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _average_ms(total_latency_ms: int, count: int) -> int | None:
    if count <= 0:
        return None
    return round(total_latency_ms / count)


def _merge_llm_usage(
    target: dict[str, int],
    usage: dict[str, object] | None,
) -> None:
    if not isinstance(usage, dict):
        return
    target["prompt_tokens"] += _safe_int(usage.get("prompt_tokens"))
    target["completion_tokens"] += _safe_int(usage.get("completion_tokens"))
    target["total_tokens"] += _safe_int(usage.get("total_tokens"))


def _breakdown_item(
    items: dict[str, dict[str, int]],
    key: object,
    *,
    tokens: int,
) -> None:
    resolved_key = str(key or "unknown")
    bucket = items.setdefault(resolved_key, {"count": 0, "total_tokens": 0})
    bucket["count"] += 1
    bucket["total_tokens"] += tokens


def _build_usage_dashboard(
    db: Session,
    *,
    days: int | None,
    from_date: date | None,
    to_date: date | None,
    limit: int,
) -> AdminUsageDashboardResponse:
    from open_work_hub_api.domains.docs.models import NativeDoc
    from open_work_hub_api.domains.meeting.models import Meeting
    from open_work_hub_api.domains.pms.models import Task
    from open_work_hub_api.domains.usage.models import UsageEvent
    from open_work_hub_api.domains.usage.service import (
        USAGE_EVENT_APP_OPEN,
        USAGE_EVENT_CONTENT_VIEW,
        USAGE_EVENT_SEARCH_QUERY,
    )
    from open_work_hub_api.domains.whiteboard.models import Whiteboard

    usage_range = _resolve_usage_date_range(
        days=days,
        from_date=from_date,
        to_date=to_date,
        max_days=MAX_USAGE_DASHBOARD_RANGE_DAYS,
    )
    since = usage_range.start_at
    until = usage_range.end_at
    target_scope = _usage_target_scope(db)
    excluded_user_ids = _usage_excluded_user_ids(db)

    user_statement = select(User).where(User.status != "system")
    if target_scope.user_ids is not None:
        user_statement = user_statement.where(User.id.in_(target_scope.user_ids))
    if excluded_user_ids:
        user_statement = user_statement.where(~User.id.in_(excluded_user_ids))
    users = db.scalars(user_statement.order_by(User.full_name.asc(), User.email.asc())).all()
    user_ids = {user.id for user in users}

    period_active_user_ids = {
        user_id
        for user_id, _occurred_at in _period_activity_rows(
            db,
            since=since,
            until=until,
            excluded_user_ids=excluded_user_ids,
            included_user_ids=user_ids,
        )
    }
    active_user_count = len(period_active_user_ids & user_ids)
    login_counts = _count_by_user(
        db,
        AuthSession,
        AuthSession.user_id,
        since=since,
        until=until,
        created_column=AuthSession.created_at,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    audit_event_counts = _count_by_user(
        db,
        AuditLog,
        AuditLog.actor_user_id,
        since=since,
        until=until,
        created_column=AuditLog.created_at,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    app_open_counts = _usage_count_by_user(
        db,
        since=since,
        until=until,
        event_type=USAGE_EVENT_APP_OPEN,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    content_view_counts = _usage_count_by_user(
        db,
        since=since,
        until=until,
        event_type=USAGE_EVENT_CONTENT_VIEW,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    search_query_counts = _usage_count_by_user(
        db,
        since=since,
        until=until,
        event_type=USAGE_EVENT_SEARCH_QUERY,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    docs_view_counts = _usage_count_by_user(
        db,
        since=since,
        until=until,
        event_type=USAGE_EVENT_CONTENT_VIEW,
        content_kind="doc",
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    whiteboards_view_counts = _usage_count_by_user(
        db,
        since=since,
        until=until,
        event_type=USAGE_EVENT_CONTENT_VIEW,
        content_kind="whiteboard",
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    usage_by_app = _usage_breakdown_counts(
        db,
        UsageEvent.app_id,
        since=since,
        until=until,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    usage_by_route = _usage_breakdown_counts(
        db,
        UsageEvent.route_path,
        since=since,
        until=until,
        event_type=USAGE_EVENT_APP_OPEN,
        exclude_empty=True,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    content_views_by_kind = _usage_breakdown_counts(
        db,
        UsageEvent.content_kind,
        since=since,
        until=until,
        event_type=USAGE_EVENT_CONTENT_VIEW,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )

    docs_owned_counts = _count_by_user(
        db,
        NativeDoc,
        NativeDoc.owner_id,
        extra_conditions=[NativeDoc.trashed_at.is_(None)],
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    docs_created_counts = _count_by_user(
        db,
        NativeDoc,
        NativeDoc.owner_id,
        since=since,
        until=until,
        created_column=NativeDoc.created_at,
        extra_conditions=[NativeDoc.trashed_at.is_(None)],
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    whiteboards_owned_counts = _count_by_user(
        db,
        Whiteboard,
        Whiteboard.owner_id,
        extra_conditions=[Whiteboard.trashed_at.is_(None)],
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    whiteboards_created_counts = _count_by_user(
        db,
        Whiteboard,
        Whiteboard.owner_id,
        since=since,
        until=until,
        created_column=Whiteboard.created_at,
        extra_conditions=[Whiteboard.trashed_at.is_(None)],
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    meeting_counts = _count_by_user(
        db,
        Meeting,
        Meeting.organizer_id,
        since=since,
        until=until,
        created_column=Meeting.created_at,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    pms_task_counts = _count_by_user(
        db,
        Task,
        Task.reporter_id,
        since=since,
        until=until,
        created_column=Task.created_at,
        extra_conditions=[Task.archived.is_(False)],
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    llm_usage_by_user: dict[str, dict[str, int]] = {}
    llm_latency_by_user: dict[str, dict[str, int]] = {}
    llm_totals = {
        "calls": 0,
        "success": 0,
        "error": 0,
        "cancelled": 0,
        "latency_ms": 0,
        "latency_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    llm_by_task: dict[str, dict[str, int]] = {}
    llm_by_model: dict[str, dict[str, int]] = {}
    llm_user_ids: set[str] = set()
    llm_rows = db.scalars(
        select(AuditLog).where(
            AuditLog.action == "llm_call",
            _usage_range_condition(AuditLog.created_at, since, until),
        )
    ).all()
    for row in llm_rows:
        payload = row.payload or {}
        actor_user_id = (
            payload.get("actor_user_id") if isinstance(payload, dict) else None
        ) or row.actor_user_id
        if not isinstance(actor_user_id, str) or actor_user_id not in user_ids:
            continue
        usage = payload.get("usage") if isinstance(payload, dict) else None
        usage_dict = usage if isinstance(usage, dict) else None
        total_tokens = _safe_int(usage_dict.get("total_tokens") if usage_dict else None)
        status_value = str(payload.get("status") if isinstance(payload, dict) else "unknown")
        latency_ms = _safe_int(payload.get("latency_ms") if isinstance(payload, dict) else None)

        llm_totals["calls"] += 1
        llm_user_ids.add(actor_user_id)
        if status_value == "ok":
            llm_totals["success"] += 1
        elif status_value == "cancelled":
            llm_totals["cancelled"] += 1
        else:
            llm_totals["error"] += 1
        if latency_ms > 0:
            llm_totals["latency_ms"] += latency_ms
            llm_totals["latency_count"] += 1
        _merge_llm_usage(llm_totals, usage_dict)

        _breakdown_item(
            llm_by_task,
            payload.get("task_kind") if isinstance(payload, dict) else None,
            tokens=total_tokens,
        )
        _breakdown_item(
            llm_by_model,
            payload.get("model") if isinstance(payload, dict) else None,
            tokens=total_tokens,
        )
        bucket = llm_usage_by_user.setdefault(
            actor_user_id,
            {"calls": 0, "total_tokens": 0},
        )
        bucket["calls"] += 1
        bucket["total_tokens"] += total_tokens
        latency_bucket = llm_latency_by_user.setdefault(
            actor_user_id,
            {"latency_ms": 0, "count": 0},
        )
        if latency_ms > 0:
            latency_bucket["latency_ms"] += latency_ms
            latency_bucket["count"] += 1

    def count_for(item: dict[str, int], user_id: str) -> int:
        return item.get(user_id, 0)

    user_items: list[AdminUsageUserItemResponse] = []
    for user in users:
        llm_user = llm_usage_by_user.get(user.id, {})
        latency_user = llm_latency_by_user.get(user.id, {})
        activity_score = (
            count_for(login_counts, user.id)
            + count_for(app_open_counts, user.id)
            + count_for(content_view_counts, user.id)
            + count_for(search_query_counts, user.id)
            + count_for(docs_created_counts, user.id)
            + count_for(whiteboards_created_counts, user.id)
            + count_for(meeting_counts, user.id)
            + count_for(pms_task_counts, user.id)
            + llm_user.get("calls", 0)
        )
        user_items.append(
            AdminUsageUserItemResponse(
                user_id=user.id,
                full_name=user.full_name,
                email=user.email,
                last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
                login_count=count_for(login_counts, user.id),
                audit_event_count=count_for(audit_event_counts, user.id),
                app_open_count=count_for(app_open_counts, user.id),
                content_view_count=count_for(content_view_counts, user.id),
                search_query_count=count_for(search_query_counts, user.id),
                docs_view_count=count_for(docs_view_counts, user.id),
                docs_owned_count=count_for(docs_owned_counts, user.id),
                docs_created_count=count_for(docs_created_counts, user.id),
                whiteboards_view_count=count_for(whiteboards_view_counts, user.id),
                whiteboards_owned_count=count_for(whiteboards_owned_counts, user.id),
                whiteboards_created_count=count_for(whiteboards_created_counts, user.id),
                meetings_created_count=count_for(meeting_counts, user.id),
                pms_tasks_created_count=count_for(pms_task_counts, user.id),
                llm_call_count=llm_user.get("calls", 0),
                llm_total_tokens=llm_user.get("total_tokens", 0),
                llm_average_latency_ms=_average_ms(
                    latency_user.get("latency_ms", 0),
                    latency_user.get("count", 0),
                ),
                activity_score=activity_score,
            )
        )

    user_items.sort(
        key=lambda item: (
            item.activity_score,
            item.last_login_at or "",
            item.full_name.lower(),
        ),
        reverse=True,
    )
    daily_trends = _build_daily_trends(
        db,
        from_date=usage_range.from_date,
        to_date=usage_range.to_date,
        since=since,
        until=until,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    hourly_access = _build_hourly_access(
        db,
        period_days=usage_range.period_days,
        since=since,
        until=until,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    token_rankings = _build_token_rankings(user_items)
    pms_summary = _build_pms_summary(
        db,
        since=since,
        until=until,
        excluded_user_ids=excluded_user_ids,
        included_user_ids=user_ids,
    )
    ai_team_summary = _build_ai_team_summary(db, since=since, until=until)
    today_visitor_count = daily_trends[-1].visitor_count if daily_trends else 0

    recent_log_statement = (
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .where(_usage_range_condition(AuditLog.created_at, since, until))
    )
    recent_log_statement = recent_log_statement.where(AuditLog.actor_user_id.in_(user_ids))
    recent_logs = db.scalars(
        recent_log_statement.order_by(AuditLog.created_at.desc()).limit(20)
    ).all()

    def sorted_breakdown(items: dict[str, dict[str, int]]) -> list[AdminUsageBreakdownItemResponse]:
        return [
            AdminUsageBreakdownItemResponse(
                key=key,
                label=key,
                count=value["count"],
                total_tokens=value["total_tokens"],
            )
            for key, value in sorted(
                items.items(),
                key=lambda row: (row[1]["count"], row[1]["total_tokens"], row[0]),
                reverse=True,
            )[:10]
        ]

    return AdminUsageDashboardResponse(
        period_days=usage_range.period_days,
        from_date=usage_range.from_date,
        to_date=usage_range.to_date,
        generated_at=usage_range.generated_at.isoformat(),
        target_scope=_serialize_usage_target_scope(target_scope, len(users)),
        totals=AdminUsageTotalsResponse(
            user_count=len(users),
            active_user_count=active_user_count,
            today_visitor_count=today_visitor_count,
            inactive_user_count=max(0, len(users) - active_user_count),
            login_count=sum(login_counts.values()),
            audit_event_count=sum(audit_event_counts.values()),
            app_open_count=sum(app_open_counts.values()),
            content_view_count=sum(content_view_counts.values()),
            search_query_count=sum(search_query_counts.values()),
            content_created_count=_sum_counts(
                docs_created_counts,
                whiteboards_created_counts,
                meeting_counts,
                pms_task_counts,
            ),
            docs_view_count=sum(docs_view_counts.values()),
            docs_owned_count=sum(docs_owned_counts.values()),
            docs_created_count=sum(docs_created_counts.values()),
            whiteboards_view_count=sum(whiteboards_view_counts.values()),
            whiteboards_owned_count=sum(whiteboards_owned_counts.values()),
            whiteboards_created_count=sum(whiteboards_created_counts.values()),
            meetings_created_count=sum(meeting_counts.values()),
            pms_tasks_created_count=sum(pms_task_counts.values()),
            llm_call_count=llm_totals["calls"],
            llm_user_count=len(llm_user_ids),
            llm_success_count=llm_totals["success"],
            llm_error_count=llm_totals["error"],
            llm_cancelled_count=llm_totals["cancelled"],
            llm_total_tokens=llm_totals["total_tokens"],
            llm_prompt_tokens=llm_totals["prompt_tokens"],
            llm_completion_tokens=llm_totals["completion_tokens"],
            llm_average_latency_ms=_average_ms(
                llm_totals["latency_ms"],
                llm_totals["latency_count"],
            ),
        ),
        users=user_items[:limit],
        daily_trends=daily_trends,
        hourly_access=hourly_access,
        token_rankings=token_rankings,
        usage_by_app=sorted_breakdown(usage_by_app),
        usage_by_route=sorted_breakdown(usage_by_route),
        content_views_by_kind=sorted_breakdown(content_views_by_kind),
        llm_by_task_kind=sorted_breakdown(llm_by_task),
        llm_by_model=sorted_breakdown(llm_by_model),
        pms_summary=pms_summary,
        ai_team_summary=ai_team_summary,
        recent_audit_logs=[_serialize_audit_log_item(item) for item in recent_logs],
    )


@router.get("/app-visibility", response_model=PlatformAppVisibilityResponse)
def list_platform_app_visibility(
    scope: AdminAppVisibilityScope = Query(default="core"),
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformAppVisibilityResponse:
    _ensure_platform_admin(context, db)
    ensure_platform_app_visibility(db)
    db.commit()
    return _serialize_platform_app_visibility(db, scope=scope)


@router.patch("/app-visibility", response_model=PlatformAppVisibilityResponse)
def update_platform_app_visibility(
    payload: PlatformAppVisibilityUpdateRequest,
    scope: AdminAppVisibilityScope = Query(default="core"),
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformAppVisibilityResponse:
    _ensure_platform_admin(context, db)
    ensure_platform_app_visibility(db)
    rows_by_app_id = _platform_app_visibility_rows_by_id(db)
    changed_items: list[dict[str, object]] = []
    now = _utcnow()

    for item in payload.items:
        catalog_item = get_workspace_app_catalog_item(item.app_id)
        if catalog_item is None or not is_platform_visibility_app(catalog_item):
            raise localized_http_exception(
                status_code=400,
                code="admin.unknown_workspace_app",
                app_id=item.app_id,
            )
        row = rows_by_app_id.get(item.app_id)
        if row is None:
            row = PlatformAppVisibility(
                id=new_id(),
                app_id=item.app_id,
                visible=item.visible,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            rows_by_app_id[item.app_id] = row
        elif row.visible != item.visible:
            row.visible = item.visible
            row.updated_at = now
            db.add(row)
        changed_items.append({"app_id": item.app_id, "visible": item.visible})

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.app_visibility.update",
        entity_kind="platform_app_visibility",
        entity_id=None,
        summary="Updated platform app visibility",
        payload={"items": changed_items},
    )
    db.commit()
    return _serialize_platform_app_visibility(db, scope=scope)


@router.get(
    "/workspaces/{workspace_id}/app-visibility",
    response_model=WorkspaceAppVisibilityResponse,
)
def list_workspace_app_visibility(
    workspace_id: str,
    scope: AdminAppVisibilityScope = Query(default="core"),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceAppVisibilityResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)
    ensure_platform_app_visibility(db)
    ensure_workspace_app_entitlements(db)
    db.commit()
    return _serialize_workspace_app_visibility(db, workspace, scope=scope)


@router.patch(
    "/workspaces/{workspace_id}/app-visibility",
    response_model=WorkspaceAppVisibilityResponse,
)
def update_workspace_app_visibility(
    workspace_id: str,
    payload: WorkspaceAppVisibilityUpdateRequest,
    scope: AdminAppVisibilityScope = Query(default="core"),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceAppVisibilityResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)
    ensure_platform_app_visibility(db)
    ensure_workspace_app_entitlements(db)
    rows_by_app_id = _workspace_app_entitlement_rows_by_id(db, workspace.id)
    changed_items: list[dict[str, object]] = []
    now = _utcnow()

    for item in payload.items:
        catalog_item = get_workspace_app_catalog_item(item.app_id)
        if (
            catalog_item is None
            or not is_app_bar_category_app(catalog_item)
            or catalog_item.availability_scope != "workspace"
        ):
            raise localized_http_exception(
                status_code=400,
                code="admin.unknown_workspace_app",
                app_id=item.app_id,
            )
        if catalog_item.platform_admin_activation_required and not is_platform_admin_user(
            context.user, db
        ):
            raise localized_http_exception(
                status_code=403,
                code="admin.platform_admin_required",
            )
        row = rows_by_app_id.get(item.app_id)
        if row is None:
            row = WorkspaceAppEntitlement(
                id=new_id(),
                workspace_id=workspace.id,
                app_id=item.app_id,
                visibility_override=item.visibility_override,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            rows_by_app_id[item.app_id] = row
        elif row.visibility_override != item.visibility_override:
            row.visibility_override = item.visibility_override
            row.updated_at = now
            db.add(row)
        changed_items.append(
            {
                "app_id": item.app_id,
                "visibility_override": item.visibility_override,
            }
        )

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace_app_visibility.update",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Updated app visibility overrides for workspace {workspace.name}",
        payload={"items": changed_items},
    )
    db.commit()
    return _serialize_workspace_app_visibility(db, workspace, scope=scope)


@router.get("/app-bar-categories", response_model=AdminAppBarCategoriesResponse)
def list_app_bar_categories(
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AdminAppBarCategoriesResponse:
    _ensure_platform_admin(context, db)
    return _serialize_admin_app_bar_categories(db)


@router.post("/app-bar-categories", response_model=AdminAppBarCategoriesResponse)
def create_app_bar_category(
    payload: AdminAppBarCategoryCreateRequest,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AdminAppBarCategoriesResponse:
    _ensure_platform_admin(context, db)
    _ensure_valid_app_bar_icon_key(payload.icon_key)
    now = _utcnow()
    category = PlatformAppBarCategory(
        id=new_id(),
        key=_next_app_bar_category_key(db),
        title=payload.title,
        icon_key=payload.icon_key,
        position=payload.position
        if payload.position is not None
        else _max_app_bar_category_position(db) + 1,
        created_at=now,
        updated_at=now,
    )
    db.add(category)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.app_bar_category.create",
        entity_kind="platform_app_bar_category",
        entity_id=category.id,
        summary=f"Created app bar category {category.title}",
        payload={"title": category.title, "icon_key": category.icon_key},
    )
    db.commit()
    return _serialize_admin_app_bar_categories(db)


@router.patch("/app-bar-categories/{category_id}", response_model=AdminAppBarCategoriesResponse)
def update_app_bar_category(
    category_id: str,
    payload: AdminAppBarCategoryUpdateRequest,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AdminAppBarCategoriesResponse:
    _ensure_platform_admin(context, db)
    category = _app_bar_category_by_id(db, category_id)
    changed: dict[str, object] = {}
    if payload.title is not None:
        category.title = payload.title
        changed["title"] = payload.title
    if payload.icon_key is not None:
        _ensure_valid_app_bar_icon_key(payload.icon_key)
        category.icon_key = payload.icon_key
        changed["icon_key"] = payload.icon_key
    if payload.position is not None:
        category.position = payload.position
        changed["position"] = payload.position
    if changed:
        category.updated_at = _utcnow()
        db.add(category)
        record_audit_log(
            db,
            actor_user_id=context.user.id,
            action="admin.app_bar_category.update",
            entity_kind="platform_app_bar_category",
            entity_id=category.id,
            summary=f"Updated app bar category {category.title}",
            payload=changed,
        )
    db.commit()
    return _serialize_admin_app_bar_categories(db)


@router.delete("/app-bar-categories/{category_id}", response_model=AdminAppBarCategoriesResponse)
def delete_app_bar_category(
    category_id: str,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AdminAppBarCategoriesResponse:
    _ensure_platform_admin(context, db)
    category = _app_bar_category_by_id(db, category_id)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.app_bar_category.delete",
        entity_kind="platform_app_bar_category",
        entity_id=category.id,
        summary=f"Deleted app bar category {category.title}",
        payload={"title": category.title},
    )
    db.delete(category)
    db.commit()
    return _serialize_admin_app_bar_categories(db)


@router.put("/app-bar-categories/layout", response_model=AdminAppBarCategoriesResponse)
def replace_app_bar_category_layout(
    payload: AdminAppBarCategoryLayoutRequest,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> AdminAppBarCategoriesResponse:
    _ensure_platform_admin(context, db)
    categories_by_id = {row.id: row for row in _app_bar_category_base_rows(db)}
    payload_category_ids = [item.id for item in payload.categories]
    if set(payload_category_ids) != set(categories_by_id):
        raise localized_http_exception(
            status_code=400,
            code="admin.invalid_app_bar_layout",
        )

    target_app_ids = set(_app_bar_category_target_catalog_items())
    seen_app_ids: set[str] = set()
    now = _utcnow()
    for item in payload.categories:
        _ensure_valid_app_bar_icon_key(item.icon_key)
        for app_id in item.app_ids:
            if app_id not in target_app_ids or app_id in seen_app_ids:
                raise localized_http_exception(
                    status_code=400,
                    code="admin.invalid_app_bar_layout",
                )
            seen_app_ids.add(app_id)

    db.execute(sa_delete(PlatformAppBarCategoryApp))
    for category_position, item in enumerate(payload.categories):
        category = categories_by_id[item.id]
        category.title = item.title
        category.icon_key = item.icon_key
        category.position = category_position
        category.updated_at = now
        for app_position, app_id in enumerate(item.app_ids):
            db.add(
                PlatformAppBarCategoryApp(
                    id=new_id(),
                    category_id=category.id,
                    app_id=app_id,
                    position=app_position,
                    created_at=now,
                    updated_at=now,
                )
            )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.app_bar_category.layout_update",
        entity_kind="platform_app_bar_category",
        entity_id=None,
        summary="Updated app bar category layout",
        payload={"category_ids": payload_category_ids},
    )
    db.commit()
    return _serialize_admin_app_bar_categories(db)


@router.get("/users", response_model=AdminUsersResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=120),
    context: AuthContext = Depends(require_permission("user.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsersResponse:
    normalized_query = q.strip() if q else ""
    user_query = select(User).where(User.status != "system")
    count_query = select(func.count()).select_from(User).where(User.status != "system")

    if normalized_query:
        search_pattern = f"%{normalized_query}%"
        search_filter = or_(
            User.login_id.ilike(search_pattern),
            User.email.ilike(search_pattern),
            User.full_name.ilike(search_pattern),
            User.display_name.ilike(search_pattern),
        )
        user_query = user_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total = db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    users = list(
        db.scalars(
            user_query.options(*ADMIN_USER_LIST_OPTIONS)
            .order_by(User.created_at.asc())
            .offset(offset)
            .limit(page_size)
        )
        .unique()
        .all()
    )
    return AdminUsersResponse(
        items=_serialize_admin_user_list(db, users),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=CreatedUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreateRequest,
    context: AuthContext = Depends(require_permission("user.write")),
    db: Session = Depends(get_db_session),
) -> CreatedUserResponse:
    email = normalize_email(payload.email)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise localized_http_exception(status_code=409, code="admin.user_already_exists")
    login_id = payload.login_id or _make_unique_login_id(db, derive_login_id_from_email(email))
    if db.scalar(select(User).where(User.login_id == login_id)) is not None:
        raise localized_http_exception(status_code=409, code="auth.login_id_already_exists")
    temporary_password = payload.temporary_password or _generate_temporary_password()
    user = User(
        id=new_id(),
        login_id=login_id,
        email=email,
        full_name=payload.full_name.strip(),
        display_name=(payload.display_name or payload.full_name).strip(),
        password_hash=hash_password(temporary_password),
        status=payload.status,
        must_change_password=True,
        theme_preference="system",
        locale=payload.locale or normalize_locale(None),
        time_zone=payload.time_zone or normalize_time_zone(None),
        date_format=payload.date_format or default_date_format_value(),
    )
    db.add(user)
    db.flush()
    replace_user_system_roles(db, user.id, payload.system_roles)
    db.flush()
    db.refresh(user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.create",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Created user {user.email}",
        payload={"system_roles": payload.system_roles},
    )
    db.commit()
    return CreatedUserResponse(
        user=_serialize_admin_user(db, user),
        temporary_password=temporary_password,
    )


@router.get("/users/{user_id}", response_model=AdminUserItemResponse)
def get_user(
    user_id: str,
    context: AuthContext = Depends(require_permission("user.read")),
    db: Session = Depends(get_db_session),
) -> AdminUserItemResponse:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    return _serialize_admin_user(db, user)


@router.patch("/users/{user_id}", response_model=AdminUserItemResponse)
def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    context: AuthContext = Depends(require_permission("user.write")),
    db: Session = Depends(get_db_session),
) -> AdminUserItemResponse:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.status is not None:
        user.status = payload.status
    if payload.login_blocked is not None:
        user.login_blocked = payload.login_blocked
        if payload.login_blocked:
            revoke_active_user_sessions(
                db,
                user_id=user.id,
                revoked_at=datetime.now(UTC).replace(tzinfo=None),
            )
    if payload.theme_preference is not None:
        user.theme_preference = payload.theme_preference
    if payload.locale is not None:
        user.locale = payload.locale
    if payload.time_zone is not None:
        user.time_zone = payload.time_zone
    if payload.date_format is not None:
        user.date_format = payload.date_format
    if payload.must_change_password is not None:
        user.must_change_password = payload.must_change_password
    if payload.system_roles is not None:
        replace_user_system_roles(db, user.id, payload.system_roles)

    db.flush()
    db.refresh(user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.update",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Updated user {user.email}",
        payload={"system_roles": payload.system_roles} if payload.system_roles is not None else {},
    )
    db.commit()
    return _serialize_admin_user(db, user)


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_user_password(
    user_id: str,
    payload: ResetPasswordRequest,
    context: AuthContext = Depends(require_permission("user.write")),
    db: Session = Depends(get_db_session),
) -> ResetPasswordResponse:
    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    temporary_password = payload.temporary_password or _generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    db.add(user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.reset-password",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Reset password for {user.email}",
    )
    db.commit()
    return ResetPasswordResponse(temporary_password=temporary_password)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    context: AuthContext = Depends(require_permission("user.write")),
    db: Session = Depends(get_db_session),
) -> None:
    if user_id == context.user.id:
        raise localized_http_exception(status_code=400, code="admin.self_delete_denied")

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    email = user.email
    db.execute(
        sa_update(AuditLog).where(AuditLog.actor_user_id == user_id).values(actor_user_id=None)
    )
    db.execute(sa_delete(AuthSession).where(AuthSession.user_id == user_id))
    db.execute(sa_delete(UserSystemRole).where(UserSystemRole.user_id == user_id))
    db.execute(sa_delete(WorkspaceUserBinding).where(WorkspaceUserBinding.user_id == user_id))
    db.execute(sa_delete(TeamMember).where(TeamMember.user_id == user_id))
    db.delete(user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.delete",
        entity_kind="user",
        entity_id=user_id,
        summary=f"Deleted user {email}",
        payload={"email": email},
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise localized_http_exception(
            status_code=409,
            code="admin.user_linked_records_delete_denied",
        ) from exc


@router.get("/workspaces", response_model=list[WorkspaceItemResponse])
def list_workspaces(
    include_archived: bool = Query(default=False),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceItemResponse]:
    is_admin = is_platform_admin_user(context.user, db)
    query = select(Workspace).options(selectinload(Workspace.teams))
    if not (include_archived and is_admin):
        query = query.where(Workspace.active.is_(True))
    query = query.order_by(Workspace.name.asc())
    items = db.scalars(query).all()
    if not is_admin:
        accessible_workspace_ids = {
            item["workspace_id"]
            for item in serialize_auth_user(db, context.user)["workspace_roles"]
        }
        items = [item for item in items if item.id in accessible_workspace_ids]
    return [_serialize_workspace(db, item) for item in items]


@router.post(
    "/workspaces", response_model=WorkspaceItemResponse, status_code=status.HTTP_201_CREATED
)
def create_workspace(
    payload: WorkspaceUpsertRequest,
    context: AuthContext = Depends(require_permission("workspace.write")),
    db: Session = Depends(get_db_session),
) -> WorkspaceItemResponse:
    workspace_id = new_id()
    key = payload.key.strip() if payload.key and payload.key.strip() else workspace_id
    if db.scalar(select(Workspace).where(Workspace.key == key)) is not None:
        raise localized_http_exception(status_code=409, code="admin.workspace_key_exists")

    workspace = Workspace(
        id=workspace_id,
        key=key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        active=payload.active,
    )
    db.add(workspace)
    db.flush()
    ensure_workspace_default_pms_space(db, workspace)
    ensure_workspace_app_entitlements(db)
    db.add(
        WorkspaceUserBinding(
            id=new_id(),
            workspace_id=workspace.id,
            user_id=context.user.id,
            role="admin",
        )
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.create",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Created workspace {workspace.name}",
    )
    db.commit()
    db.refresh(workspace)
    return _serialize_workspace(db, workspace)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceItemResponse)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceItemResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    workspace.key = payload.key or workspace.key
    workspace.name = payload.name.strip()
    workspace.description = payload.description.strip()
    workspace.active = payload.active
    db.add(workspace)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.update",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Updated workspace {workspace.name}",
    )
    db.commit()
    db.refresh(workspace)
    return _serialize_workspace(db, workspace)


@router.get(
    "/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse]
)
def list_workspace_bindings(
    workspace_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
    _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    workspace = db.scalar(
        select(Workspace)
        .options(selectinload(Workspace.user_bindings).joinedload(WorkspaceUserBinding.user))
        .where(Workspace.id == workspace_id)
    )
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")

    items = [
        WorkspaceBindingItemResponse(
            subject_id=binding.user_id,
            subject_type="user",
            subject_label=binding.user.full_name or binding.user.email,
            subject_secondary=binding.user.email,
            role=normalize_workspace_role(binding.role) or binding.role,
        )
        for binding in workspace.user_bindings
    ]
    return items


@router.put(
    "/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse]
)
def replace_workspace_bindings(
    workspace_id: str,
    payload: WorkspaceBindingsUpdateRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
    _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    workspace = db.scalar(
        select(Workspace)
        .options(selectinload(Workspace.user_bindings))
        .where(Workspace.id == workspace_id)
    )
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")

    user_role_map = {item.subject_id: item.role for item in payload.users}
    replace_workspace_member_bindings(
        db,
        workspace,
        actor_user_id=context.user.id,
        requested_roles_by_user_id=user_role_map,
    )

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.bindings.replace",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Replaced workspace bindings for {workspace.name}",
    )
    db.commit()
    return list_workspace_bindings(workspace_id, context, db)


def _serialize_user_binding(binding: WorkspaceUserBinding) -> WorkspaceBindingItemResponse:
    item = serialize_workspace_member_binding(binding)
    return WorkspaceBindingItemResponse(
        subject_id=item.subject_id,
        subject_type=item.subject_type,
        subject_label=item.subject_label,
        subject_secondary=item.subject_secondary,
        role=item.role,
    )


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceBindingItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_workspace_member(
    workspace_id: str,
    payload: WorkspaceMemberUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceBindingItemResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    binding = add_workspace_member_binding(
        db,
        workspace,
        subject_id=payload.subject_id,
        role=payload.role,
        duplicate_code="admin.user_already_workspace_member",
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.member.add",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Added user to {workspace.name}",
        payload={"subject_type": "user", "subject_id": payload.subject_id, "role": payload.role},
    )
    db.commit()
    return _serialize_user_binding(binding)


@router.patch(
    "/workspaces/{workspace_id}/members/{subject_type}/{subject_id}",
    response_model=WorkspaceBindingItemResponse,
)
def update_workspace_member_role(
    workspace_id: str,
    subject_type: Literal["user"],
    subject_id: str,
    payload: WorkspaceMemberRoleUpdateRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceBindingItemResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    binding = update_workspace_member_binding_role(
        db,
        workspace,
        actor_user_id=context.user.id,
        subject_id=subject_id,
        role=payload.role,
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.member.role.update",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Changed user role in {workspace.name}",
        payload={"subject_type": "user", "subject_id": subject_id, "role": payload.role},
    )
    db.commit()
    return _serialize_user_binding(binding)


@router.delete(
    "/workspaces/{workspace_id}/members/{subject_type}/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_workspace_member(
    workspace_id: str,
    subject_type: Literal["user"],
    subject_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    remove_workspace_member_binding(
        db,
        workspace,
        actor_user_id=context.user.id,
        subject_id=subject_id,
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.member.remove",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Removed {subject_type} from {workspace.name}",
        payload={"subject_type": subject_type, "subject_id": subject_id},
    )
    db.commit()


@router.get(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMembersResponse,
)
def list_workspace_members(
    workspace_id: str,
    q: str | None = Query(default=None, max_length=120),
    role: list[str] | None = Query(default=None),
    subject_type: Literal["user"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    pending_only: bool = Query(default=False),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceMembersResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    normalized_query = q.strip() if q else ""
    directory = list_workspace_member_directory(
        db,
        workspace,
        query=normalized_query,
        role_filters=role,
        subject_type=subject_type,
        page=page,
        page_size=page_size,
        pending_only=pending_only,
    )
    return WorkspaceMembersResponse(
        items=[WorkspaceMemberItemResponse(**asdict(item)) for item in directory.items],
        total=directory.total,
        page=directory.page,
        page_size=directory.page_size,
        role_counts=WorkspaceMemberRoleCounts(**directory.role_counts),
        user_count=directory.user_count,
        pending_count=directory.pending_count,
    )


@router.post(
    "/workspaces/{workspace_id}/members/bulk",
    response_model=WorkspaceMemberBulkResponse,
)
def bulk_workspace_members(
    workspace_id: str,
    payload: WorkspaceMemberBulkRequest,
    request: Request,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceMemberBulkResponse:
    workspace = _ensure_admin_workspace_scope(db, context.user, workspace_id)

    succeeded = 0
    failed: list[dict[str, str]] = []

    for entry in payload.subjects:
        savepoint = db.begin_nested()
        try:
            apply_workspace_member_bulk_entry(
                db,
                workspace,
                actor_user_id=context.user.id,
                action=payload.action,
                subject_type=entry.subject_type,
                subject_id=entry.subject_id,
                role=entry.role,
            )
            db.flush()
            savepoint.commit()
            succeeded += 1
        except HTTPException as exc:
            savepoint.rollback()
            failure = {
                "subject_type": entry.subject_type,
                "subject_id": entry.subject_id,
                "detail": _exception_detail(exc, request),
            }
            if code := _exception_code(exc):
                failure["code"] = code
            failed.append(failure)

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action=f"admin.workspace.members.bulk.{payload.action}",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Bulk {payload.action} on {workspace.name}",
        payload={"succeeded": succeeded, "failed_count": len(failed)},
    )
    db.commit()
    return WorkspaceMemberBulkResponse(succeeded=succeeded, failed=failed)


@router.get(
    "/workspaces/{workspace_id}/member-candidates",
    response_model=list[WorkspaceMemberCandidateResponse],
)
def list_workspace_member_candidates(
    workspace_id: str,
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceMemberCandidateResponse]:
    _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")

    normalized_query = q.strip() if q else ""
    query = (
        select(User).where(User.status.in_(("active", "invited"))).order_by(User.full_name.asc())
    )
    if normalized_query:
        search_pattern = f"%{normalized_query}%"
        query = query.where(
            or_(
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern),
                User.display_name.ilike(search_pattern),
            )
        )
    users = db.scalars(query.limit(limit)).all()
    return [
        WorkspaceMemberCandidateResponse(
            id=item.id,
            email=item.email,
            full_name=item.full_name,
            display_name=item.display_name or item.full_name,
            status=item.status,
        )
        for item in users
    ]


@router.get("/teams", response_model=list[TeamItemResponse])
def list_teams(
    workspace_id: str | None = None,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[TeamItemResponse]:
    query = (
        select(Team)
        .options(joinedload(Team.workspace), selectinload(Team.members))
        .where(Team.trashed_at.is_(None))
    )
    if workspace_id:
        _ensure_workspace_scope(db, context.user, workspace_id, min_role="member")
        query = query.where(Team.workspace_id == workspace_id)
    items = db.scalars(query.order_by(Team.name.asc())).all()
    if not is_platform_admin_user(context.user, db) and workspace_id is None:
        accessible_workspace_ids = {
            item["workspace_id"]
            for item in serialize_auth_user(db, context.user)["workspace_roles"]
        }
        items = [item for item in items if item.workspace_id in accessible_workspace_ids]
    return [
        TeamItemResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            workspace_key=item.workspace.key,
            key=item.key,
            name=item.name,
            description=item.description,
            active=item.active,
            member_count=len(item.members),
            current_user_role=resolve_team_role(db, context.user, item),
        )
        for item in items
    ]


@router.post(
    "/workspaces/{workspace_id}/teams",
    response_model=TeamItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_team(
    workspace_id: str,
    payload: TeamUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> TeamItemResponse:
    workspace = _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    key = payload.key or slugify(payload.name)
    if (
        db.scalar(select(Team).where(Team.workspace_id == workspace.id, Team.key == key))
        is not None
    ):
        raise localized_http_exception(status_code=409, code="admin.team_key_exists")

    team = Team(
        id=new_id(),
        workspace_id=workspace.id,
        key=key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        active=payload.active,
    )
    db.add(team)
    db.flush()
    db.add(
        TeamMember(
            id=new_id(),
            team_id=team.id,
            user_id=context.user.id,
            role="owner",
        )
    )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.team.create",
        entity_kind="team",
        entity_id=team.id,
        summary=f"Created team {team.name}",
    )
    db.commit()
    return TeamItemResponse(
        id=team.id,
        workspace_id=team.workspace_id,
        workspace_key=workspace.key,
        key=team.key,
        name=team.name,
        description=team.description,
        active=team.active,
        member_count=1,
        current_user_role="owner",
    )


@router.patch("/teams/{team_id}", response_model=TeamItemResponse)
def update_team(
    team_id: str,
    payload: TeamUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> TeamItemResponse:
    team = _ensure_team_scope(
        db,
        context.user,
        team_id,
        min_role="admin",
        include_workspace=True,
        include_members=True,
    )
    team.key = payload.key or team.key
    team.name = payload.name.strip()
    team.description = payload.description.strip()
    team.active = payload.active
    db.add(team)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.team.update",
        entity_kind="team",
        entity_id=team.id,
        summary=f"Updated team {team.name}",
    )
    db.commit()
    return TeamItemResponse(
        id=team.id,
        workspace_id=team.workspace_id,
        workspace_key=team.workspace.key,
        key=team.key,
        name=team.name,
        description=team.description,
        active=team.active,
        member_count=len(team.members),
        current_user_role=resolve_team_role(db, context.user, team),
    )


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    team = _ensure_team_scope(db, context.user, team_id, min_role="admin")
    team.trashed_at = _utcnow()
    db.add(team)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.team.delete",
        entity_kind="team",
        entity_id=team.id,
        summary=f"Moved team {team.name} to trash",
    )
    db.commit()


@router.get("/teams/{team_id}/members", response_model=list[AdminUserItemResponse])
def list_team_members(
    team_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[AdminUserItemResponse]:
    team = _ensure_team_scope(
        db,
        context.user,
        team_id,
        min_role="member",
        include_members=True,
    )
    members = db.scalars(
        select(User)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team.id)
        .order_by(User.full_name.asc())
    ).all()
    return [_serialize_admin_user(db, member) for member in members]


@router.put("/teams/{team_id}/members", response_model=list[AdminUserItemResponse])
def replace_team_members(
    team_id: str,
    payload: TeamMembersUpdateRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[AdminUserItemResponse]:
    team = _ensure_team_scope(
        db,
        context.user,
        team_id,
        min_role="admin",
        include_members=True,
    )

    requested_ids = set(payload.user_ids)
    current_ids = {member.user_id for member in team.members}
    for member in list(team.members):
        if member.user_id not in requested_ids:
            db.delete(member)
    for user_id in requested_ids - current_ids:
        if db.scalar(select(User.id).where(User.id == user_id)) is not None:
            db.add(TeamMember(id=new_id(), team_id=team.id, user_id=user_id))

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.team.members.replace",
        entity_kind="team",
        entity_id=team.id,
        summary=f"Replaced members for team {team.name}",
        payload={"user_ids": sorted(requested_ids)},
    )
    db.commit()
    return list_team_members(team_id, context, db)


@router.get("/ai-security/summary", response_model=AiSecuritySummaryResponse)
def get_ai_security_summary(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecuritySummaryResponse:
    _ensure_platform_admin(context, db)
    rules = _serialize_ai_security_rules(db)
    exceptions = _serialize_ai_security_exceptions(db)
    return AiSecuritySummaryResponse(
        external_app_candidates=_ai_security_external_app_candidates(),
        data_protection=_serialize_ai_security_data_protection(db),
        rules=rules,
        exceptions=exceptions,
        condition_options=_ai_security_condition_options(),
        active_rule_count=sum(1 for rule in rules if rule.enabled),
        active_exception_count=sum(1 for exception in exceptions if exception.enabled),
        audit_log_count_24h=_ai_security_audit_log_count_24h(db),
    )


@router.get("/ai-security/monitoring", response_model=AiSecurityMonitoringResponse)
def get_ai_security_monitoring(
    days: int | None = Query(default=7, ge=1, le=3650),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityMonitoringResponse:
    _ensure_platform_admin(context, db)
    return _build_ai_security_monitoring(
        db,
        days=days,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )


@router.get(
    "/ai-security/detected-values/groups",
    response_model=AiSecurityDetectedValueGroupsResponse,
)
def list_ai_security_detected_value_groups(
    days: int | None = Query(default=7, ge=1, le=3650),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    privacy_filter: bool = Query(default=False),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityDetectedValueGroupsResponse:
    _ensure_platform_admin(context, db)
    usage_range = _resolve_usage_date_range(
        days=days,
        from_date=from_date,
        to_date=to_date,
        max_days=MAX_AUDIT_LOG_RANGE_DAYS,
    )
    return _ai_security_detected_value_groups(
        db,
        start_at=usage_range.start_at,
        end_at=usage_range.end_at,
        privacy_filter=privacy_filter,
        limit=limit,
        offset=offset,
        query=q,
    )


@router.get(
    "/ai-security/detected-values/details",
    response_model=AiSecurityDetectedValueDetailsResponse,
)
def list_ai_security_detected_value_details(
    detector: str = Query(..., min_length=1, max_length=64),
    entity_type: str = Query(..., min_length=1, max_length=120),
    blocker_type: str = Query(..., min_length=1, max_length=80),
    days: int | None = Query(default=7, ge=1, le=3650),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityDetectedValueDetailsResponse:
    _ensure_platform_admin(context, db)
    usage_range = _resolve_usage_date_range(
        days=days,
        from_date=from_date,
        to_date=to_date,
        max_days=MAX_AUDIT_LOG_RANGE_DAYS,
    )
    return _ai_security_detected_value_details(
        db,
        start_at=usage_range.start_at,
        end_at=usage_range.end_at,
        detector=detector,
        entity_type=entity_type,
        blocker_type=blocker_type,
        limit=limit,
        offset=offset,
        query=q,
    )


@router.get("/ai-security/data-protection", response_model=AiSecurityDataProtectionResponse)
def get_ai_security_data_protection(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityDataProtectionResponse:
    _ensure_platform_admin(context, db)
    return _serialize_ai_security_data_protection(db)


@router.put("/ai-security/data-protection", response_model=AiSecurityDataProtectionResponse)
def update_ai_security_data_protection(
    payload: AiSecurityDataProtectionUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityDataProtectionResponse:
    _ensure_platform_admin(context, db)
    settings = get_or_create_ai_security_data_protection_settings(
        db,
        updated_by=context.user.id,
    )
    terms = normalize_custom_block_terms(payload.custom_block_terms)
    blocker_actions = normalize_ai_security_blocker_actions(payload.blocker_actions)
    external_app_actions = normalize_ai_security_external_app_actions(payload.external_app_actions)
    settings.custom_block_terms_json = terms
    settings.blocker_actions_json = blocker_actions
    settings.external_app_actions_json = external_app_actions
    settings.updated_by = context.user.id
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.data_protection.update",
        entity_kind="ai_security",
        entity_id=DATA_PROTECTION_SETTINGS_ID,
        summary="Updated AI security data protection settings",
        payload={
            "custom_block_term_count": len(terms),
            "blocker_actions": blocker_actions,
            "external_app_actions": external_app_actions,
        },
    )
    db.commit()
    return _serialize_ai_security_data_protection(db)


@router.patch("/ai-security/enforcement", response_model=AiSecurityDataProtectionResponse)
def update_ai_security_enforcement(
    payload: AiSecurityEnforcementUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityDataProtectionResponse:
    _ensure_platform_admin(context, db)
    settings = get_or_create_ai_security_data_protection_settings(
        db,
        updated_by=context.user.id,
    )
    reason = payload.enforcement_disabled_reason.strip()
    settings.enforcement_enabled = payload.enforcement_enabled
    settings.enforcement_disabled_reason = "" if payload.enforcement_enabled else reason
    settings.updated_by = context.user.id
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.enforcement.update",
        entity_kind="ai_security",
        entity_id=DATA_PROTECTION_SETTINGS_ID,
        summary=(
            "Enabled AI security gateway enforcement"
            if payload.enforcement_enabled
            else "Disabled AI security gateway enforcement"
        ),
        payload={
            "enforcement_enabled": payload.enforcement_enabled,
            "enforcement_disabled_reason": settings.enforcement_disabled_reason,
        },
    )
    db.commit()
    return _serialize_ai_security_data_protection(db)


@router.get("/ai-security/rules", response_model=AiSecurityPolicyRulesResponse)
def list_ai_security_policy_rules(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityPolicyRulesResponse:
    _ensure_platform_admin(context, db)
    return AiSecurityPolicyRulesResponse(items=_serialize_ai_security_rules(db))


@router.post(
    "/ai-security/rules",
    response_model=AiSecurityPolicyRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_security_policy_rule(
    payload: AiSecurityPolicyRuleUpsertRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityPolicyRuleResponse:
    _ensure_platform_admin(context, db)
    _validate_ai_security_rule_references(db, payload)
    rule = AiSecurityPolicyRule(
        id=new_id(),
        name=payload.name.strip(),
        description="",
        enabled=payload.enabled,
        effect="inherit",
        created_by=context.user.id,
        updated_by=context.user.id,
    )
    _apply_ai_security_rule_payload(rule, payload, actor_user_id=context.user.id)
    db.add(rule)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.rule.create",
        entity_kind="ai_security_policy_rule",
        entity_id=rule.id,
        summary=f"Created AI security policy rule {rule.name}",
        payload=_ai_security_rule_audit_payload(rule),
    )
    db.commit()
    return _serialize_ai_security_rule(rule, _ai_security_rule_label_maps(db, [rule]))


@router.patch("/ai-security/rules/{rule_id}", response_model=AiSecurityPolicyRuleResponse)
def update_ai_security_policy_rule(
    rule_id: str,
    payload: AiSecurityPolicyRuleUpsertRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityPolicyRuleResponse:
    _ensure_platform_admin(context, db)
    rule = db.get(AiSecurityPolicyRule, rule_id)
    if rule is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.ai_security_rule_not_found",
        )
    _validate_ai_security_rule_references(db, payload)
    _apply_ai_security_rule_payload(rule, payload, actor_user_id=context.user.id)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.rule.update",
        entity_kind="ai_security_policy_rule",
        entity_id=rule.id,
        summary=f"Updated AI security policy rule {rule.name}",
        payload=_ai_security_rule_audit_payload(rule),
    )
    db.commit()
    return _serialize_ai_security_rule(rule, _ai_security_rule_label_maps(db, [rule]))


@router.delete("/ai-security/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_security_policy_rule(
    rule_id: str,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> None:
    _ensure_platform_admin(context, db)
    rule = db.get(AiSecurityPolicyRule, rule_id)
    if rule is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.ai_security_rule_not_found",
        )
    audit_payload = _ai_security_rule_audit_payload(rule)
    rule_name = rule.name
    db.delete(rule)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.rule.delete",
        entity_kind="ai_security_policy_rule",
        entity_id=rule_id,
        summary=f"Deleted AI security policy rule {rule_name}",
        payload=audit_payload,
    )
    db.commit()
    return None


@router.get(
    "/ai-security/exceptions",
    response_model=AiSecurityExternalTransferExceptionsResponse,
)
def list_ai_security_external_transfer_exceptions(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityExternalTransferExceptionsResponse:
    _ensure_platform_admin(context, db)
    return AiSecurityExternalTransferExceptionsResponse(items=_serialize_ai_security_exceptions(db))


@router.post(
    "/ai-security/exceptions",
    response_model=AiSecurityExternalTransferExceptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_security_external_transfer_exception(
    payload: AiSecurityExternalTransferExceptionUpsertRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityExternalTransferExceptionResponse:
    _ensure_platform_admin(context, db)
    _validate_ai_security_rule_references(db, payload)
    exception = AiSecurityExternalTransferException(
        id=new_id(),
        name=payload.name.strip(),
        description="",
        enabled=payload.enabled,
        reason="",
        created_by=context.user.id,
        updated_by=context.user.id,
    )
    _apply_ai_security_exception_payload(exception, payload, actor_user_id=context.user.id)
    db.add(exception)
    db.flush()
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.external_transfer_exception.create",
        entity_kind="ai_security_external_transfer_exception",
        entity_id=exception.id,
        summary=f"Created AI security external transfer exception {exception.name}",
        payload=_ai_security_exception_audit_payload(exception),
    )
    db.commit()
    return _serialize_ai_security_exception(
        exception,
        _ai_security_exception_label_maps(db, [exception]),
    )


@router.patch(
    "/ai-security/exceptions/{exception_id}",
    response_model=AiSecurityExternalTransferExceptionResponse,
)
def update_ai_security_external_transfer_exception(
    exception_id: str,
    payload: AiSecurityExternalTransferExceptionUpsertRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecurityExternalTransferExceptionResponse:
    _ensure_platform_admin(context, db)
    exception = db.get(AiSecurityExternalTransferException, exception_id)
    if exception is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.ai_security_exception_not_found",
        )
    _validate_ai_security_rule_references(db, payload)
    _apply_ai_security_exception_payload(exception, payload, actor_user_id=context.user.id)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.external_transfer_exception.update",
        entity_kind="ai_security_external_transfer_exception",
        entity_id=exception.id,
        summary=f"Updated AI security external transfer exception {exception.name}",
        payload=_ai_security_exception_audit_payload(exception),
    )
    db.commit()
    return _serialize_ai_security_exception(
        exception,
        _ai_security_exception_label_maps(db, [exception]),
    )


@router.delete("/ai-security/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ai_security_external_transfer_exception(
    exception_id: str,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> None:
    _ensure_platform_admin(context, db)
    exception = db.get(AiSecurityExternalTransferException, exception_id)
    if exception is None:
        raise localized_http_exception(
            status_code=404,
            code="admin.ai_security_exception_not_found",
        )
    audit_payload = _ai_security_exception_audit_payload(exception)
    exception_name = exception.name
    db.delete(exception)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_security.external_transfer_exception.delete",
        entity_kind="ai_security_external_transfer_exception",
        entity_id=exception_id,
        summary=f"Deleted AI security external transfer exception {exception_name}",
        payload=audit_payload,
    )
    db.commit()
    return None


@router.post("/ai-security/simulate", response_model=AiSecuritySimulationResponse)
def simulate_ai_security_policy(
    payload: AiSecuritySimulationRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiSecuritySimulationResponse:
    _ensure_platform_admin(context, db)
    sample_texts = [payload.sample_text or ""]
    if not ai_security_enforcement_enabled(db):
        return AiSecuritySimulationResponse(
            effect="inherit",
            rule_id=None,
            rule_name=None,
            reason_code=AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
            route_action="unchanged",
            allow_external=True,
            forced_local=False,
            blocked_entity_types=[],
            external_transfer_blocker_types=[],
            hard_blocker_types=[],
            external_transfer_exception_allowed=False,
            pii_hits=[],
            sensitivity_labels=list(normalize_external_safety_values(payload.sensitivity_labels)),
            content_origin=normalize_content_origin(payload.content_origin),
            source_kinds=list(normalize_external_safety_values(payload.source_kinds)),
            custom_block_term_count=0,
            matched_scope={},
            mask_applied=False,
            masked_entity_types=[],
            masked_text_preview=None,
            privacy_filter_status=None,
        )
    security_decision = evaluate_ai_security_policy(
        db,
        AiSecurityPolicyContext(
            workspace_id=payload.workspace_id,
            actor_user_id=payload.actor_user_id,
            app_id=payload.app_id,
            task_kind=payload.task_kind,
            capability=payload.capability,
            provider=payload.provider,
        ),
        sample_texts,
    )
    safety = evaluate_external_payload_safety(
        sample_texts,
        content_origin=payload.content_origin,
        source_kinds=tuple(payload.source_kinds),
        sensitivity_labels=tuple(payload.sensitivity_labels),
    )
    external_transfer_blockers = external_transfer_blockers_from_safety(
        safety,
        custom_block_term_count=security_decision.custom_block_term_count,
        policy_block_external=security_decision.effect == "block_external",
    )
    exception_decision = AiSecurityExternalTransferExceptionDecision()
    masking_result = None
    hard_blockers = hard_external_transfer_blockers(external_transfer_blockers)
    is_llm_capability = not payload.capability or payload.capability == AI_SECURITY_LLM_CAPABILITY
    external_app_actions = ai_security_external_app_actions(db)
    is_configured_external_app = (
        payload.app_id is not None and payload.app_id in external_app_actions
    )
    if external_transfer_blockers:
        exception_decision = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                workspace_id=payload.workspace_id,
                actor_user_id=payload.actor_user_id,
                app_id=payload.app_id,
                task_kind=payload.task_kind,
                capability=payload.capability,
                provider=payload.provider,
            ),
            external_transfer_blockers,
        )
    if exception_decision.allowed:
        route_action = "external_exception"
    elif security_decision.effect == "block_external":
        route_action = "blocked"
    elif hard_blockers:
        route_action = "blocked"
    elif security_decision.effect == "mask_and_send":
        masking_result = evaluate_external_payload_masking(
            sample_texts,
            safety_decision=safety,
            custom_block_term_count=security_decision.custom_block_term_count,
        )
        route_action = "masked_external" if masking_result.allowed else "blocked"
    else:
        if is_llm_capability:
            if is_configured_external_app:
                global_action = ai_security_external_app_action_for_blockers(
                    db,
                    payload.app_id,
                    external_transfer_blockers,
                )
            else:
                global_action = _ai_security_global_action_for_blockers(
                    db,
                    external_transfer_blockers,
                )
        else:
            global_action = ai_security_external_app_action_for_blockers(
                db,
                payload.app_id,
                external_transfer_blockers,
            )
        if global_action == "mask_and_send":
            masking_result = evaluate_external_payload_masking(
                sample_texts,
                safety_decision=safety,
                custom_block_term_count=security_decision.custom_block_term_count,
            )
            route_action = "masked_external" if masking_result.allowed else "blocked"
        elif global_action == "block":
            route_action = "blocked"
        else:
            if not safety.allow_external or security_decision.custom_block_term_count > 0:
                route_action = "blocked"
            else:
                route_action = _ai_security_route_action(
                    policy_effect=security_decision.effect,
                    safety_allow_external=safety.allow_external,
                    custom_block_term_count=security_decision.custom_block_term_count,
                    external_transfer_exception_allowed=False,
                )
    blocked_entity_types = list(safety.blocked_entity_types)
    if security_decision.custom_block_term_count > 0:
        blocked_entity_types.append(CUSTOM_BLOCK_ENTITY_TYPE)
    if masking_result is not None:
        blocked_entity_types.extend(masking_result.masked_entity_types)
        blocked_entity_types.extend(masking_result.blocker_types)
    simulation_blockers = tuple(
        normalize_external_transfer_blockers(
            (
                *external_transfer_blockers,
                *(masking_result.blocker_types if masking_result is not None else ()),
            )
        )
    )
    hard_blockers = tuple(
        normalize_external_transfer_blockers(
            (
                *hard_external_transfer_blockers(simulation_blockers),
                *(masking_result.hard_blocker_types if masking_result is not None else ()),
            )
        )
    )
    return AiSecuritySimulationResponse(
        effect=security_decision.effect,
        rule_id=security_decision.rule_id,
        rule_name=security_decision.rule_name,
        reason_code=(
            EXTERNAL_TRANSFER_EXCEPTION_REASON
            if route_action == "external_exception"
            else (
                masking_result.reason_code
                if masking_result is not None
                else (
                    security_decision.reason_code if safety.allow_external else safety.reason_code
                )
            )
        ),
        route_action=route_action,
        allow_external=route_action in {"unchanged", "external_exception", "masked_external"}
        and security_decision.effect != "block_external"
        and (
            safety.allow_external
            or exception_decision.allowed
            or (masking_result.allowed if masking_result is not None else False)
        ),
        forced_local=False,
        blocked_entity_types=sorted(set(blocked_entity_types)),
        external_transfer_blocker_types=list(simulation_blockers),
        hard_blocker_types=list(hard_blockers),
        external_transfer_exception_allowed=exception_decision.allowed,
        external_transfer_exception_id=exception_decision.exception_id,
        external_transfer_exception_name=exception_decision.exception_name,
        external_transfer_exception_reason=(
            exception_decision.reason_code if exception_decision.allowed else None
        ),
        pii_hits=sorted(
            {
                *safety.pii_hits,
                *(masking_result.pii_hits if masking_result is not None else ()),
            }
        ),
        sensitivity_labels=list(safety.sensitivity_labels),
        content_origin=safety.content_origin,
        source_kinds=list(safety.source_kinds),
        custom_block_term_count=security_decision.custom_block_term_count,
        matched_scope=security_decision.matched_scope,
        mask_applied=masking_result.mask_applied if masking_result is not None else False,
        masked_entity_types=(
            sorted(set(masking_result.masked_entity_types)) if masking_result is not None else []
        ),
        masked_text_preview=(
            masking_result.masked_texts[0][:1000]
            if masking_result is not None
            and masking_result.mask_applied
            and masking_result.masked_texts
            else None
        ),
        privacy_filter_status=(
            masking_result.privacy_filter_status if masking_result is not None else None
        ),
    )


@router.get("/usage/dashboard", response_model=AdminUsageDashboardResponse)
def get_usage_dashboard(
    days: int = Query(default=7, ge=1, le=365),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsageDashboardResponse:
    _ensure_platform_admin(context, db)
    return _build_usage_dashboard(
        db,
        days=days,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )


@router.get("/usage/excluded-users", response_model=list[AdminUsageExcludedUserItemResponse])
def list_usage_excluded_users(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> list[AdminUsageExcludedUserItemResponse]:
    _ensure_platform_admin(context, db)
    return _serialize_usage_excluded_users(db)


@router.put("/usage/excluded-users", response_model=list[AdminUsageExcludedUserItemResponse])
def replace_usage_excluded_users(
    payload: AdminUsageExcludedUsersUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> list[AdminUsageExcludedUserItemResponse]:
    from open_work_hub_api.domains.usage.models import UsageExcludedUser

    _ensure_platform_admin(context, db)
    user_ids = list(dict.fromkeys(item.strip() for item in payload.user_ids if item.strip()))
    if user_ids:
        existing_user_ids = set(db.scalars(select(User.id).where(User.id.in_(user_ids))).all())
        if existing_user_ids != set(user_ids):
            raise localized_http_exception(status_code=404, code="auth.user_not_found")
    else:
        existing_user_ids = set()

    current_user_ids = _usage_excluded_user_ids(db)
    to_remove = current_user_ids - existing_user_ids
    to_add = existing_user_ids - current_user_ids

    if to_remove:
        db.execute(sa_delete(UsageExcludedUser).where(UsageExcludedUser.user_id.in_(to_remove)))
    for user_id in sorted(to_add):
        db.add(
            UsageExcludedUser(
                user_id=user_id,
                created_by_user_id=context.user.id,
            )
        )

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.usage_exclusions.update",
        entity_kind="usage_excluded_users",
        entity_id=None,
        summary=f"Updated usage excluded users: {len(existing_user_ids)} users",
        payload={
            "user_ids": sorted(existing_user_ids),
            "added_user_ids": sorted(to_add),
            "removed_user_ids": sorted(to_remove),
        },
    )
    db.commit()
    return _serialize_usage_excluded_users(db)


@router.get("/usage/targets", response_model=AdminUsageTargetsResponse)
def get_usage_targets(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsageTargetsResponse:
    _ensure_platform_admin(context, db)
    return _serialize_usage_targets(db)


@router.put("/usage/targets", response_model=AdminUsageTargetsResponse)
def replace_usage_targets(
    payload: AdminUsageTargetsUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsageTargetsResponse:
    from open_work_hub_api.domains.usage.models import UsageTargetUser

    _ensure_platform_admin(context, db)
    user_ids = list(dict.fromkeys(item.strip() for item in payload.user_ids if item.strip()))
    if user_ids:
        existing_user_ids = set(
            db.scalars(select(User.id).where(User.status != "system", User.id.in_(user_ids))).all()
        )
        if existing_user_ids != set(user_ids):
            raise localized_http_exception(status_code=404, code="auth.user_not_found")
    else:
        existing_user_ids = set()

    current_user_ids = set(db.scalars(select(UsageTargetUser.user_id)).all())
    user_ids_to_remove = current_user_ids - existing_user_ids
    user_ids_to_add = existing_user_ids - current_user_ids

    if user_ids_to_remove:
        db.execute(
            sa_delete(UsageTargetUser).where(UsageTargetUser.user_id.in_(user_ids_to_remove))
        )
    for user_id in sorted(user_ids_to_add):
        db.add(
            UsageTargetUser(
                user_id=user_id,
                created_by_user_id=context.user.id,
            )
        )
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.usage_targets.update",
        entity_kind="usage_targets",
        entity_id=None,
        summary=f"Updated usage targets: {len(existing_user_ids)} users",
        payload={
            "user_ids": sorted(existing_user_ids),
            "added_user_ids": sorted(user_ids_to_add),
            "removed_user_ids": sorted(user_ids_to_remove),
        },
    )
    db.commit()
    return _serialize_usage_targets(db)


@router.get("/audit-logs", response_model=AuditLogsResponse)
def list_audit_logs(
    days: int | None = Query(default=None, ge=1, le=3650),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_kind: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=120),
    ai_security_only: bool = Query(default=False),
    ai_security_blocked_only: bool = Query(default=False),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AuditLogsResponse:
    _ensure_platform_admin(context, db)
    filters = []
    if days is not None or from_date is not None or to_date is not None:
        usage_range = _resolve_usage_date_range(
            days=days,
            from_date=from_date,
            to_date=to_date,
            max_days=MAX_AUDIT_LOG_RANGE_DAYS,
        )
        filters.append(
            _usage_range_condition(
                AuditLog.created_at,
                usage_range.start_at,
                usage_range.end_at,
            )
        )
    if actor_user_id:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if action:
        filters.append(AuditLog.action == action)
    if entity_kind:
        filters.append(AuditLog.entity_kind == entity_kind)
    if ai_security_only:
        filters.append(_ai_security_audit_action_condition())
    query_text = q.strip() if q else ""
    if query_text:
        pattern = f"%{query_text}%"
        query_filters = [
            AuditLog.summary.ilike(pattern),
            AuditLog.action.ilike(pattern),
            AuditLog.entity_kind.ilike(pattern),
            AuditLog.entity_id.ilike(pattern),
        ]
        if query_text.lower().replace("-", "_") == "ai_security":
            query_filters.append(_ai_security_audit_action_condition())
        filters.append(or_(*query_filters))
    if ai_security_blocked_only:
        filters.append(_ai_security_runtime_audit_action_condition())
    count_statement = select(func.count(AuditLog.id))
    statement = select(AuditLog).options(joinedload(AuditLog.actor))
    if filters:
        count_statement = count_statement.where(*filters)
        statement = statement.where(*filters)
    if ai_security_blocked_only:
        filtered_items = [
            item
            for item in db.scalars(
                statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            ).all()
            if _ai_security_blocked_or_forced_log(item)
        ]
        total = len(filtered_items)
        items = filtered_items[offset : offset + limit]
        next_offset = offset + len(items)
        return AuditLogsResponse(
            items=[_serialize_audit_log_item(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
            next_offset=next_offset if next_offset < total else None,
        )
    total = db.scalar(count_statement) or 0
    items = db.scalars(
        statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    next_offset = offset + len(items)
    return AuditLogsResponse(
        items=[_serialize_audit_log_item(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset if next_offset < total else None,
    )


@router.post(
    "/ai/runtime/retention/scrub",
    response_model=AiRuntimeRetentionScrubResponse,
)
def scrub_ai_runtime_retention_payloads(
    older_than_days: int | None = Query(default=None, ge=1, le=3650),
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> AiRuntimeRetentionScrubResponse:
    if not is_platform_admin_user(context.user, db):
        raise localized_http_exception(status_code=403, code="admin.platform_admin_required")

    retention_days = older_than_days or get_settings().ai_runtime_retention_days
    scrubbed_count = scrub_completed_runtime_records(db, older_than_days=retention_days)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_runtime.retention.scrub",
        entity_kind="ai_runtime",
        entity_id="retention",
        summary=f"Scrubbed {scrubbed_count} AI runtime run(s)",
        payload={"older_than_days": retention_days, "scrubbed_run_count": scrubbed_count},
    )
    db.commit()
    return AiRuntimeRetentionScrubResponse(
        scrubbed_run_count=scrubbed_count,
        older_than_days=retention_days,
    )
