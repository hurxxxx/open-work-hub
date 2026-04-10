from __future__ import annotations

from datetime import UTC, datetime
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import (
    APP_FEATURE_CODES,
    SYSTEM_ORG_ADMIN,
    SYSTEM_PLATFORM_ADMIN,
    SYSTEM_ROLE_ORDER,
    WORKSPACE_ROLE_RANK,
    assign_user_groups,
    is_org_admin_user,
    is_platform_admin_user,
    is_valid_workspace_role,
    load_user_graph,
    load_active_workspace_by_id,
    normalize_workspace_role,
    replace_group_system_roles,
    replace_user_system_roles,
    record_audit_log,
    resolve_team_role,
    resolve_workspace_role,
    serialize_auth_user,
    serialize_org_unit,
    slugify,
    team_role_allows,
    workspace_role_allows,
)
from aidoo_api.domains.auth.dependencies import AuthContext, require_auth_context, require_permission
from aidoo_api.domains.auth.models import (
    AccessGroup,
    AuditLog,
    FeaturePolicy,
    OrgUnit,
    Team,
    TeamMember,
    User,
    UserAccessGroup,
    Workspace,
    WorkspaceGroupBinding,
    WorkspaceUserBinding,
)
from aidoo_api.domains.auth.security import hash_password, new_id, normalize_email


class OrgUnitItemResponse(BaseModel):
    id: str
    name: str
    slug: str
    parent_id: str | None
    active: bool


class AccessGroupItemResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: str
    group_kind: str
    active: bool
    system_roles: list[str]
    member_count: int


class WorkspaceItemResponse(BaseModel):
    id: str
    key: str
    name: str
    description: str
    active: bool
    team_count: int


class WorkspaceBindingItemResponse(BaseModel):
    subject_id: str
    subject_type: Literal["user", "group"]
    subject_label: str
    role: str


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


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _visible_team_count(workspace: Workspace) -> int:
    return sum(1 for team in workspace.teams if team.trashed_at is None)


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
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if is_platform_admin_user(user, db) or is_org_admin_user(user, db):
        return workspace

    role = resolve_workspace_role(db, user, workspace.id)
    if not workspace_role_allows(role, min_role):
        raise HTTPException(status_code=403, detail="Workspace access required.")
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
        raise HTTPException(status_code=404, detail="Team not found.")
    if is_platform_admin_user(user, db) or is_org_admin_user(user, db):
        return team
    role = resolve_team_role(db, user, team)
    if not team_role_allows(role, min_role):
        raise HTTPException(status_code=403, detail="Team access required.")
    return team


class FeaturePolicyItemResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    enabled: bool
    allowed_workspace_keys: list[str]


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


class AdminUserItemResponse(BaseModel):
    id: str
    email: str
    full_name: str
    display_name: str
    status: str
    theme_preference: str
    primary_org_unit: dict[str, str | None] | None
    system_roles: list[str]
    workspace_roles: list[dict[str, str]]
    app_access: list[dict[str, str | None]]
    group_ids: list[str]
    group_slugs: list[str]
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


class OrgUnitUpsertRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    parent_id: str | None = None
    active: bool = True


class AccessGroupUpsertRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=1000)
    group_kind: str = Field(default="principal", max_length=24)
    active: bool = True
    system_roles: list[str] = Field(default_factory=list)


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
            raise ValueError("Invalid workspace role.")
        normalized = normalize_workspace_role(value)
        assert normalized is not None
        return normalized


class WorkspaceBindingsUpdateRequest(BaseModel):
    users: list[WorkspaceBindingInput] = Field(default_factory=list)
    groups: list[WorkspaceBindingInput] = Field(default_factory=list)


class TeamMembersUpdateRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class AdminUserCreateRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    full_name: str = Field(..., min_length=2, max_length=120)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    primary_org_unit_id: str | None = None
    group_ids: list[str] = Field(default_factory=list)
    system_roles: list[str] = Field(default_factory=list)
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    status: Literal["active", "invited", "suspended"] = "active"


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    primary_org_unit_id: str | None = None
    group_ids: list[str] | None = None
    system_roles: list[str] | None = None
    status: Literal["active", "invited", "suspended"] | None = None
    theme_preference: Literal["system", "light", "dark"] | None = None
    must_change_password: bool | None = None


class ResetPasswordRequest(BaseModel):
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)


class ResetPasswordResponse(BaseModel):
    temporary_password: str


class FeaturePolicyUpdateItem(BaseModel):
    id: str
    enabled: bool


class FeaturePolicyUpdateRequest(BaseModel):
    items: list[FeaturePolicyUpdateItem]


router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_USER_LIST_OPTIONS = (
    joinedload(User.primary_org_unit),
    selectinload(User.system_role_links),
    selectinload(User.group_links)
    .joinedload(UserAccessGroup.group)
    .selectinload(AccessGroup.system_role_links),
    selectinload(User.group_links)
    .joinedload(UserAccessGroup.group)
    .selectinload(AccessGroup.workspace_bindings)
    .joinedload(WorkspaceGroupBinding.workspace),
    selectinload(User.workspace_bindings).joinedload(WorkspaceUserBinding.workspace),
)


def _generate_temporary_password() -> str:
    return f"Aidoo!{secrets.token_urlsafe(10)}"


def _serialize_admin_user(db: Session, user: User) -> AdminUserItemResponse:
    loaded = load_user_graph(db, user.id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return AdminUserItemResponse.model_validate(serialize_auth_user(db, loaded))


def _sort_system_roles(roles: set[str]) -> list[str]:
    ordered = [role for role in SYSTEM_ROLE_ORDER if role in roles]
    extras = sorted(role for role in roles if role not in SYSTEM_ROLE_ORDER)
    return ordered + extras


def _resolve_loaded_system_roles(user: User) -> list[str]:
    roles = {
        link.role
        for link in user.system_role_links
        if link.role in {SYSTEM_PLATFORM_ADMIN, SYSTEM_ORG_ADMIN}
    }

    for link in user.group_links:
        if not link.group.active:
            continue
        roles.update(
            system_link.role
            for system_link in link.group.system_role_links
            if system_link.role in {SYSTEM_PLATFORM_ADMIN, SYSTEM_ORG_ADMIN}
        )

    if user.is_admin:
        roles.add(SYSTEM_PLATFORM_ADMIN)

    return _sort_system_roles(roles)


def _resolve_loaded_workspace_role_map(
    user: User,
    system_roles: set[str],
    active_workspace_ids: set[str],
) -> dict[str, str]:
    if SYSTEM_PLATFORM_ADMIN in system_roles:
        return {workspace_id: "admin" for workspace_id in active_workspace_ids}

    role_map: dict[str, str] = {}
    for binding in user.workspace_bindings:
        normalized_role = normalize_workspace_role(binding.role)
        if (
            normalized_role is None
            or binding.workspace_id not in active_workspace_ids
            or not binding.workspace.active
        ):
            continue
        role_map[binding.workspace_id] = normalized_role

    for link in user.group_links:
        if not link.group.active:
            continue
        for binding in link.group.workspace_bindings:
            normalized_role = normalize_workspace_role(binding.role)
            if (
                normalized_role is None
                or binding.workspace_id not in active_workspace_ids
                or not binding.workspace.active
            ):
                continue
            current_role = role_map.get(binding.workspace_id)
            if (
                current_role is None
                or WORKSPACE_ROLE_RANK[normalized_role] > WORKSPACE_ROLE_RANK[current_role]
            ):
                role_map[binding.workspace_id] = normalized_role

    return role_map


def _resolve_docs_native_user_ids(db: Session, user_ids: set[str]) -> set[str]:
    if not user_ids:
        return set()

    from aidoo_api.domains.docs.models import NativeDoc, NativeDocUserShare

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
    workspaces = list(db.scalars(select(Workspace).where(Workspace.active.is_(True))).all())
    workspace_by_id = {workspace.id: workspace for workspace in workspaces}
    workspace_by_key = {workspace.key: workspace for workspace in workspaces}
    active_workspace_ids = set(workspace_by_id)
    enabled_policies = {
        policy.code: policy
        for policy in db.scalars(select(FeaturePolicy).where(FeaturePolicy.enabled.is_(True))).all()
    }
    docs_native_user_ids = _resolve_docs_native_user_ids(db, {user.id for user in users})

    items: list[AdminUserItemResponse] = []
    for user in users:
        system_roles = _resolve_loaded_system_roles(user)
        system_role_set = set(system_roles)
        workspace_role_map = _resolve_loaded_workspace_role_map(
            user,
            system_role_set,
            active_workspace_ids,
        )
        workspace_roles = [
            {
                "workspace_id": workspace.id,
                "key": workspace.key,
                "name": workspace.name,
                "role": role,
            }
            for workspace in sorted(workspaces, key=lambda item: item.key)
            if (role := workspace_role_map.get(workspace.id)) is not None
        ]
        workspace_roles_by_key = {item["key"]: item for item in workspace_roles}
        app_access: list[dict[str, str | None]] = []

        for app_code, feature_code in APP_FEATURE_CODES.items():
            if feature_code not in enabled_policies:
                continue

            if app_code == "admin":
                if not system_roles:
                    continue
                workspace = workspace_roles_by_key.get("admin")
                app_access.append(
                    {
                        "app": "admin",
                        "workspace_id": workspace["workspace_id"] if workspace else None,
                        "workspace_key": "admin",
                        "workspace_name": workspace["name"] if workspace else "Admin Console",
                        "role": "admin",
                    }
                )
                continue

            workspace = workspace_roles_by_key.get(app_code)
            if app_code == "docs" and workspace is None and user.id in docs_native_user_ids:
                docs_workspace = workspace_by_key.get("docs")
                if docs_workspace is not None:
                    app_access.append(
                        {
                            "app": "docs",
                            "workspace_id": docs_workspace.id,
                            "workspace_key": docs_workspace.key,
                            "workspace_name": docs_workspace.name,
                            "role": "member",
                        }
                    )
                continue

            if app_code == "pms" and workspace is None and SYSTEM_ORG_ADMIN in system_role_set:
                pms_workspace = workspace_by_key.get("pms")
                if pms_workspace is not None:
                    app_access.append(
                        {
                            "app": "pms",
                            "workspace_id": pms_workspace.id,
                            "workspace_key": pms_workspace.key,
                            "workspace_name": pms_workspace.name,
                            "role": "admin",
                        }
                    )
                continue

            if workspace is None:
                continue
            app_access.append(
                {
                    "app": app_code,
                    "workspace_id": workspace["workspace_id"],
                    "workspace_key": workspace["key"],
                    "workspace_name": workspace["name"],
                    "role": workspace["role"],
                }
            )

        items.append(
            AdminUserItemResponse.model_validate(
                {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "display_name": user.display_name or user.full_name,
                    "status": user.status,
                    "theme_preference": user.theme_preference,
                    "primary_org_unit": serialize_org_unit(user.primary_org_unit),
                    "system_roles": system_roles,
                    "workspace_roles": workspace_roles,
                    "app_access": app_access,
                    "group_ids": sorted(
                        {link.group_id for link in user.group_links if link.group.active}
                    ),
                    "group_slugs": sorted(
                        {link.group.slug for link in user.group_links if link.group.active}
                    ),
                    "must_change_password": user.must_change_password,
                    "last_login_at": user.last_login_at,
                    "created_at": user.created_at,
                }
            )
        )

    return items


@router.get("/users", response_model=AdminUsersResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=120),
    context: AuthContext = Depends(require_permission("user.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsersResponse:
    normalized_query = q.strip() if q else ""
    user_query = select(User)
    count_query = select(func.count()).select_from(User)

    if normalized_query:
        search_pattern = f"%{normalized_query}%"
        search_filter = or_(
            User.email.ilike(search_pattern),
            User.full_name.ilike(search_pattern),
            User.display_name.ilike(search_pattern),
            User.employee_code.ilike(search_pattern),
            User.job_title.ilike(search_pattern),
            OrgUnit.name.ilike(search_pattern),
        )
        user_query = user_query.outerjoin(OrgUnit, User.primary_org_unit_id == OrgUnit.id).where(
            search_filter
        )
        count_query = count_query.outerjoin(OrgUnit, User.primary_org_unit_id == OrgUnit.id).where(
            search_filter
        )

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
        raise HTTPException(status_code=409, detail="User already exists.")

    temporary_password = payload.temporary_password or _generate_temporary_password()
    user = User(
        id=new_id(),
        email=email,
        full_name=payload.full_name.strip(),
        display_name=(payload.display_name or payload.full_name).strip(),
        employee_code=payload.employee_code.strip() if payload.employee_code else None,
        job_title=payload.job_title.strip() if payload.job_title else None,
        password_hash=hash_password(temporary_password),
        status=payload.status,
        primary_org_unit_id=payload.primary_org_unit_id,
        must_change_password=True,
        theme_preference="system",
    )
    db.add(user)
    db.flush()
    assign_user_groups(db, user, payload.group_ids)
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
        payload={"group_ids": payload.group_ids, "system_roles": payload.system_roles},
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
        raise HTTPException(status_code=404, detail="User not found.")
    return _serialize_admin_user(db, user)


@router.patch("/users/{user_id}", response_model=AdminUserItemResponse)
def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    context: AuthContext = Depends(require_permission("user.write")),
    db: Session = Depends(get_db_session),
) -> AdminUserItemResponse:
    user = db.scalar(select(User).options(selectinload(User.group_links)).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip()
    if payload.display_name is not None:
        user.display_name = payload.display_name.strip()
    if payload.employee_code is not None:
        user.employee_code = payload.employee_code.strip() or None
    if payload.job_title is not None:
        user.job_title = payload.job_title.strip() or None
    if payload.status is not None:
        user.status = payload.status
    if payload.theme_preference is not None:
        user.theme_preference = payload.theme_preference
    if payload.primary_org_unit_id is not None:
        user.primary_org_unit_id = payload.primary_org_unit_id
    if payload.must_change_password is not None:
        user.must_change_password = payload.must_change_password
    if payload.group_ids is not None:
        assign_user_groups(db, user, payload.group_ids)
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
        raise HTTPException(status_code=404, detail="User not found.")

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


@router.get("/org-units", response_model=list[OrgUnitItemResponse])
def list_org_units(
    context: AuthContext = Depends(require_permission("org_unit.read")),
    db: Session = Depends(get_db_session),
) -> list[OrgUnitItemResponse]:
    items = db.scalars(select(OrgUnit).order_by(OrgUnit.name.asc())).all()
    return [
        OrgUnitItemResponse(
            id=item.id,
            name=item.name,
            slug=item.slug,
            parent_id=item.parent_id,
            active=item.active,
        )
        for item in items
    ]


@router.post("/org-units", response_model=OrgUnitItemResponse, status_code=status.HTTP_201_CREATED)
def create_org_unit(
    payload: OrgUnitUpsertRequest,
    context: AuthContext = Depends(require_permission("org_unit.write")),
    db: Session = Depends(get_db_session),
) -> OrgUnitItemResponse:
    slug = payload.slug or slugify(payload.name)
    if db.scalar(select(OrgUnit).where(OrgUnit.slug == slug)) is not None:
        raise HTTPException(status_code=409, detail="Org unit slug already exists.")

    org_unit = OrgUnit(
        id=new_id(),
        name=payload.name.strip(),
        slug=slug,
        parent_id=payload.parent_id,
        active=payload.active,
    )
    db.add(org_unit)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.org-unit.create",
        entity_kind="org-unit",
        entity_id=org_unit.id,
        summary=f"Created org unit {org_unit.name}",
    )
    db.commit()
    return OrgUnitItemResponse(
        id=org_unit.id,
        name=org_unit.name,
        slug=org_unit.slug,
        parent_id=org_unit.parent_id,
        active=org_unit.active,
    )


@router.patch("/org-units/{org_unit_id}", response_model=OrgUnitItemResponse)
def update_org_unit(
    org_unit_id: str,
    payload: OrgUnitUpsertRequest,
    context: AuthContext = Depends(require_permission("org_unit.write")),
    db: Session = Depends(get_db_session),
) -> OrgUnitItemResponse:
    org_unit = db.scalar(select(OrgUnit).where(OrgUnit.id == org_unit_id))
    if org_unit is None:
        raise HTTPException(status_code=404, detail="Org unit not found.")

    org_unit.name = payload.name.strip()
    org_unit.slug = payload.slug or slugify(payload.name)
    org_unit.parent_id = payload.parent_id
    org_unit.active = payload.active
    db.add(org_unit)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.org-unit.update",
        entity_kind="org-unit",
        entity_id=org_unit.id,
        summary=f"Updated org unit {org_unit.name}",
    )
    db.commit()
    return OrgUnitItemResponse(
        id=org_unit.id,
        name=org_unit.name,
        slug=org_unit.slug,
        parent_id=org_unit.parent_id,
        active=org_unit.active,
    )


@router.get("/groups", response_model=list[AccessGroupItemResponse])
def list_groups(
    context: AuthContext = Depends(require_permission("group.read")),
    db: Session = Depends(get_db_session),
) -> list[AccessGroupItemResponse]:
    groups = db.scalars(
        select(AccessGroup).options(
            selectinload(AccessGroup.members),
            selectinload(AccessGroup.system_role_links),
        )
    ).all()
    return [
        AccessGroupItemResponse(
            id=group.id,
            name=group.name,
            slug=group.slug,
            description=group.description,
            group_kind=group.group_kind,
            active=group.active,
            system_roles=sorted({link.role for link in group.system_role_links}),
            member_count=len(group.members),
        )
        for group in groups
    ]


@router.post("/groups", response_model=AccessGroupItemResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: AccessGroupUpsertRequest,
    context: AuthContext = Depends(require_permission("group.write")),
    db: Session = Depends(get_db_session),
) -> AccessGroupItemResponse:
    slug = payload.slug or slugify(payload.name)
    if db.scalar(select(AccessGroup).where(AccessGroup.slug == slug)) is not None:
        raise HTTPException(status_code=409, detail="Group slug already exists.")

    group = AccessGroup(
        id=new_id(),
        name=payload.name.strip(),
        slug=slug,
        description=payload.description.strip(),
        group_kind=payload.group_kind,
        active=payload.active,
        permissions=[],
    )
    db.add(group)
    db.flush()
    replace_group_system_roles(db, group.id, payload.system_roles)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.create",
        entity_kind="group",
        entity_id=group.id,
        summary=f"Created principal group {group.name}",
        payload={"system_roles": payload.system_roles},
    )
    db.commit()
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        system_roles=sorted(payload.system_roles),
        member_count=0,
    )


@router.patch("/groups/{group_id}", response_model=AccessGroupItemResponse)
def update_group(
    group_id: str,
    payload: AccessGroupUpsertRequest,
    context: AuthContext = Depends(require_permission("group.write")),
    db: Session = Depends(get_db_session),
) -> AccessGroupItemResponse:
    group = db.scalar(
        select(AccessGroup)
        .options(selectinload(AccessGroup.members), selectinload(AccessGroup.system_role_links))
        .where(AccessGroup.id == group_id)
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    group.name = payload.name.strip()
    group.slug = payload.slug or slugify(payload.name)
    group.description = payload.description.strip()
    group.group_kind = payload.group_kind
    group.active = payload.active
    group.permissions = []
    replace_group_system_roles(db, group.id, payload.system_roles)
    db.add(group)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.update",
        entity_kind="group",
        entity_id=group.id,
        summary=f"Updated principal group {group.name}",
        payload={"system_roles": payload.system_roles},
    )
    db.commit()
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        system_roles=sorted(payload.system_roles),
        member_count=len(group.members),
    )


@router.put("/groups/{group_id}/members", response_model=AccessGroupItemResponse)
def replace_group_members(
    group_id: str,
    payload: TeamMembersUpdateRequest,
    context: AuthContext = Depends(require_permission("group.write")),
    db: Session = Depends(get_db_session),
) -> AccessGroupItemResponse:
    group = db.scalar(
        select(AccessGroup)
        .options(selectinload(AccessGroup.members), selectinload(AccessGroup.system_role_links))
        .where(AccessGroup.id == group_id)
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    requested_ids = set(payload.user_ids)
    current_ids = {link.user_id for link in group.members}
    for link in list(group.members):
        if link.user_id not in requested_ids:
            db.delete(link)
    for user_id in requested_ids - current_ids:
        if db.scalar(select(User.id).where(User.id == user_id)) is not None:
            db.add(UserAccessGroup(id=new_id(), user_id=user_id, group_id=group.id))

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.members.replace",
        entity_kind="group",
        entity_id=group.id,
        summary=f"Replaced group membership for {group.name}",
        payload={"user_ids": sorted(requested_ids)},
    )
    db.commit()
    group = db.scalar(
        select(AccessGroup)
        .options(selectinload(AccessGroup.members), selectinload(AccessGroup.system_role_links))
        .where(AccessGroup.id == group_id)
    )
    assert group is not None
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        system_roles=sorted({link.role for link in group.system_role_links}),
        member_count=len(group.members),
    )


@router.get("/workspaces", response_model=list[WorkspaceItemResponse])
def list_workspaces(
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceItemResponse]:
    query = select(Workspace).options(selectinload(Workspace.teams)).where(Workspace.active.is_(True))
    items = db.scalars(query).all()
    if not (is_platform_admin_user(context.user, db) or is_org_admin_user(context.user, db)):
        accessible_workspace_ids = {
            item["workspace_id"]
            for item in serialize_auth_user(db, context.user)["workspace_roles"]
        }
        items = [item for item in items if item.id in accessible_workspace_ids]
    return [
        WorkspaceItemResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            active=item.active,
            team_count=_visible_team_count(item),
        )
        for item in items
    ]


@router.post("/workspaces", response_model=WorkspaceItemResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceUpsertRequest,
    context: AuthContext = Depends(require_permission("workspace.write")),
    db: Session = Depends(get_db_session),
) -> WorkspaceItemResponse:
    key = payload.key or slugify(payload.name)
    if db.scalar(select(Workspace).where(Workspace.key == key)) is not None:
        raise HTTPException(status_code=409, detail="Workspace key already exists.")

    workspace = Workspace(
        id=new_id(),
        key=key,
        name=payload.name.strip(),
        description=payload.description.strip(),
        active=payload.active,
    )
    db.add(workspace)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.workspace.create",
        entity_kind="workspace",
        entity_id=workspace.id,
        summary=f"Created workspace {workspace.name}",
    )
    db.commit()
    return WorkspaceItemResponse(
        id=workspace.id,
        key=workspace.key,
        name=workspace.name,
        description=workspace.description,
        active=workspace.active,
        team_count=0,
    )


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceItemResponse)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> WorkspaceItemResponse:
    workspace = _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    workspace = db.scalar(select(Workspace).options(selectinload(Workspace.teams)).where(Workspace.id == workspace.id))
    assert workspace is not None

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
    return WorkspaceItemResponse(
        id=workspace.id,
        key=workspace.key,
        name=workspace.name,
        description=workspace.description,
        active=workspace.active,
        team_count=_visible_team_count(workspace),
    )


@router.get("/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse])
def list_workspace_bindings(
    workspace_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
    _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    workspace = db.scalar(
        select(Workspace)
        .options(
            selectinload(Workspace.user_bindings).joinedload(WorkspaceUserBinding.user),
            selectinload(Workspace.group_bindings).joinedload(WorkspaceGroupBinding.group),
        )
        .where(Workspace.id == workspace_id)
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    items = [
        WorkspaceBindingItemResponse(
            subject_id=binding.user_id,
            subject_type="user",
            subject_label=binding.user.email,
            role="member"
            if workspace.key == "pms"
            else (normalize_workspace_role(binding.role) or binding.role),
        )
        for binding in workspace.user_bindings
    ]
    items.extend(
        WorkspaceBindingItemResponse(
            subject_id=binding.group_id,
            subject_type="group",
            subject_label=binding.group.name,
            role="member"
            if workspace.key == "pms"
            else (normalize_workspace_role(binding.role) or binding.role),
        )
        for binding in workspace.group_bindings
    )
    return items


@router.put("/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse])
def replace_workspace_bindings(
    workspace_id: str,
    payload: WorkspaceBindingsUpdateRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
    _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")
    workspace = db.scalar(
        select(Workspace)
        .options(
            selectinload(Workspace.user_bindings),
            selectinload(Workspace.group_bindings),
        )
        .where(Workspace.id == workspace_id)
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    requested_user_ids = {item.subject_id for item in payload.users}
    requested_group_ids = {item.subject_id for item in payload.groups}
    normalized_role = (lambda role: "member" if workspace.key == "pms" else role)
    user_role_map = {item.subject_id: normalized_role(item.role) for item in payload.users}
    group_role_map = {item.subject_id: normalized_role(item.role) for item in payload.groups}

    for binding in list(workspace.user_bindings):
        if binding.user_id not in requested_user_ids:
            db.delete(binding)
        else:
            binding.role = user_role_map[binding.user_id]
            db.add(binding)
    existing_user_ids = {binding.user_id for binding in workspace.user_bindings}
    for user_id in requested_user_ids - existing_user_ids:
        if db.scalar(select(User.id).where(User.id == user_id)) is not None:
            db.add(
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=user_id,
                    role=user_role_map[user_id],
                )
            )

    for binding in list(workspace.group_bindings):
        if binding.group_id not in requested_group_ids:
            db.delete(binding)
        else:
            binding.role = group_role_map[binding.group_id]
            db.add(binding)
    existing_group_ids = {binding.group_id for binding in workspace.group_bindings}
    for group_id in requested_group_ids - existing_group_ids:
        if db.scalar(select(AccessGroup.id).where(AccessGroup.id == group_id)) is not None:
            db.add(
                WorkspaceGroupBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    group_id=group_id,
                    role=group_role_map[group_id],
                )
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
    if not (
        is_platform_admin_user(context.user, db)
        or is_org_admin_user(context.user, db)
    ) and workspace_id is None:
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


@router.post("/workspaces/{workspace_id}/teams", response_model=TeamItemResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    workspace_id: str,
    payload: TeamUpsertRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> TeamItemResponse:
    workspace = _ensure_workspace_scope(db, context.user, workspace_id, min_role="admin")

    key = payload.key or slugify(payload.name)
    if db.scalar(select(Team).where(Team.workspace_id == workspace.id, Team.key == key)) is not None:
        raise HTTPException(status_code=409, detail="Team key already exists in workspace.")

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


@router.get("/feature-policies", response_model=list[FeaturePolicyItemResponse])
def list_feature_policies(
    context: AuthContext = Depends(require_permission("feature_policy.read")),
    db: Session = Depends(get_db_session),
) -> list[FeaturePolicyItemResponse]:
    items = db.scalars(select(FeaturePolicy).order_by(FeaturePolicy.code.asc())).all()
    return [
        FeaturePolicyItemResponse(
            id=item.id,
            code=item.code,
            name=item.name,
            description=item.description,
            enabled=item.enabled,
            allowed_workspace_keys=list(item.allowed_workspace_keys or []),
        )
        for item in items
    ]


@router.put("/feature-policies", response_model=list[FeaturePolicyItemResponse])
def update_feature_policies(
    payload: FeaturePolicyUpdateRequest,
    context: AuthContext = Depends(require_permission("feature_policy.write")),
    db: Session = Depends(get_db_session),
) -> list[FeaturePolicyItemResponse]:
    policies = {
        item.id: item for item in db.scalars(select(FeaturePolicy)).all()
    }
    for update in payload.items:
        policy = policies.get(update.id)
        if policy is None:
            continue
        policy.enabled = update.enabled
        db.add(policy)

    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.feature-policy.update",
        entity_kind="feature-policy",
        summary="Updated feature policies",
        payload={"ids": [item.id for item in payload.items]},
    )
    db.commit()
    return list_feature_policies(context, db)


@router.get("/audit-logs", response_model=list[AuditLogItemResponse])
def list_audit_logs(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> list[AuditLogItemResponse]:
    items = db.scalars(
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    ).all()
    return [
        AuditLogItemResponse(
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
        for item in items
    ]
