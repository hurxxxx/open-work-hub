from __future__ import annotations

from datetime import datetime
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import (
    assign_user_groups,
    load_user_graph,
    record_audit_log,
    serialize_auth_user,
    slugify,
)
from aidoo_api.domains.auth.dependencies import AuthContext, require_permission
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
    permissions: list[str]
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


class FeaturePolicyItemResponse(BaseModel):
    id: str
    code: str
    name: str
    description: str
    enabled: bool
    required_permissions: list[str]
    allowed_workspace_keys: list[str]
    allowed_group_slugs: list[str]


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
    workspace_roles: list[dict[str, str]]
    group_ids: list[str]
    group_slugs: list[str]
    permissions: list[str]
    visible_features: list[str]
    must_change_password: bool
    is_admin: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminUsersResponse(BaseModel):
    items: list[AdminUserItemResponse]


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
    group_kind: str = Field(default="access", max_length=24)
    active: bool = True
    permissions: list[str] = Field(default_factory=list)


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
    temporary_password: str | None = Field(default=None, min_length=8, max_length=128)
    status: Literal["active", "invited", "suspended"] = "active"


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    employee_code: str | None = Field(default=None, max_length=40)
    job_title: str | None = Field(default=None, max_length=120)
    primary_org_unit_id: str | None = None
    group_ids: list[str] | None = None
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
    required_permissions: list[str] = Field(default_factory=list)
    allowed_workspace_keys: list[str] = Field(default_factory=list)
    allowed_group_slugs: list[str] = Field(default_factory=list)


class FeaturePolicyUpdateRequest(BaseModel):
    items: list[FeaturePolicyUpdateItem]


router = APIRouter(prefix="/admin", tags=["admin"])


def _generate_temporary_password() -> str:
    return f"Aidoo!{secrets.token_urlsafe(10)}"


def _serialize_admin_user(db: Session, user: User) -> AdminUserItemResponse:
    loaded = load_user_graph(db, user.id)
    if loaded is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return AdminUserItemResponse.model_validate(serialize_auth_user(db, loaded))


def _sync_is_admin(db: Session, user: User) -> None:
    platform_admin = db.scalar(select(AccessGroup).where(AccessGroup.slug == "platform-admin"))
    if platform_admin is None:
        return
    user.is_admin = any(link.group_id == platform_admin.id for link in user.group_links)
    db.add(user)


@router.get("/users", response_model=AdminUsersResponse)
def list_users(
    context: AuthContext = Depends(require_permission("user.read")),
    db: Session = Depends(get_db_session),
) -> AdminUsersResponse:
    users = db.scalars(select(User).order_by(User.created_at.asc())).all()
    return AdminUsersResponse(items=[_serialize_admin_user(db, user) for user in users])


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
    db.flush()
    db.refresh(user)
    _sync_is_admin(db, user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.create",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Created user {user.email}",
        payload={"group_ids": payload.group_ids},
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

    db.flush()
    db.refresh(user)
    _sync_is_admin(db, user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.user.update",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Updated user {user.email}",
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
    groups = db.scalars(select(AccessGroup).options(selectinload(AccessGroup.members))).all()
    return [
        AccessGroupItemResponse(
            id=group.id,
            name=group.name,
            slug=group.slug,
            description=group.description,
            group_kind=group.group_kind,
            active=group.active,
            permissions=list(group.permissions or []),
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
        permissions=payload.permissions,
    )
    db.add(group)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.create",
        entity_kind="group",
        entity_id=group.id,
        summary=f"Created access group {group.name}",
    )
    db.commit()
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        permissions=list(group.permissions or []),
        member_count=0,
    )


@router.patch("/groups/{group_id}", response_model=AccessGroupItemResponse)
def update_group(
    group_id: str,
    payload: AccessGroupUpsertRequest,
    context: AuthContext = Depends(require_permission("group.write")),
    db: Session = Depends(get_db_session),
) -> AccessGroupItemResponse:
    group = db.scalar(select(AccessGroup).options(selectinload(AccessGroup.members)).where(AccessGroup.id == group_id))
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found.")

    group.name = payload.name.strip()
    group.slug = payload.slug or slugify(payload.name)
    group.description = payload.description.strip()
    group.group_kind = payload.group_kind
    group.active = payload.active
    group.permissions = payload.permissions
    db.add(group)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.group.update",
        entity_kind="group",
        entity_id=group.id,
        summary=f"Updated access group {group.name}",
    )
    db.commit()
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        permissions=list(group.permissions or []),
        member_count=len(group.members),
    )


@router.put("/groups/{group_id}/members", response_model=AccessGroupItemResponse)
def replace_group_members(
    group_id: str,
    payload: TeamMembersUpdateRequest,
    context: AuthContext = Depends(require_permission("group.write")),
    db: Session = Depends(get_db_session),
) -> AccessGroupItemResponse:
    group = db.scalar(select(AccessGroup).options(selectinload(AccessGroup.members)).where(AccessGroup.id == group_id))
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
    group = db.scalar(select(AccessGroup).options(selectinload(AccessGroup.members)).where(AccessGroup.id == group_id))
    assert group is not None
    return AccessGroupItemResponse(
        id=group.id,
        name=group.name,
        slug=group.slug,
        description=group.description,
        group_kind=group.group_kind,
        active=group.active,
        permissions=list(group.permissions or []),
        member_count=len(group.members),
    )


@router.get("/workspaces", response_model=list[WorkspaceItemResponse])
def list_workspaces(
    context: AuthContext = Depends(require_permission("workspace.read")),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceItemResponse]:
    items = db.scalars(select(Workspace).options(selectinload(Workspace.teams))).all()
    return [
        WorkspaceItemResponse(
            id=item.id,
            key=item.key,
            name=item.name,
            description=item.description,
            active=item.active,
            team_count=len(item.teams),
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
    context: AuthContext = Depends(require_permission("workspace.write")),
    db: Session = Depends(get_db_session),
) -> WorkspaceItemResponse:
    workspace = db.scalar(select(Workspace).options(selectinload(Workspace.teams)).where(Workspace.id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

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
        team_count=len(workspace.teams),
    )


@router.get("/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse])
def list_workspace_bindings(
    workspace_id: str,
    context: AuthContext = Depends(require_permission("workspace.read")),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
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
            role=binding.role,
        )
        for binding in workspace.user_bindings
    ]
    items.extend(
        WorkspaceBindingItemResponse(
            subject_id=binding.group_id,
            subject_type="group",
            subject_label=binding.group.name,
            role=binding.role,
        )
        for binding in workspace.group_bindings
    )
    return items


@router.put("/workspaces/{workspace_id}/bindings", response_model=list[WorkspaceBindingItemResponse])
def replace_workspace_bindings(
    workspace_id: str,
    payload: WorkspaceBindingsUpdateRequest,
    context: AuthContext = Depends(require_permission("workspace.write")),
    db: Session = Depends(get_db_session),
) -> list[WorkspaceBindingItemResponse]:
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
    user_role_map = {item.subject_id: item.role for item in payload.users}
    group_role_map = {item.subject_id: item.role for item in payload.groups}

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
    context: AuthContext = Depends(require_permission("team.read")),
    db: Session = Depends(get_db_session),
) -> list[TeamItemResponse]:
    query = select(Team).options(joinedload(Team.workspace), selectinload(Team.members))
    if workspace_id:
        query = query.where(Team.workspace_id == workspace_id)
    items = db.scalars(query.order_by(Team.name.asc())).all()
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
        )
        for item in items
    ]


@router.post("/workspaces/{workspace_id}/teams", response_model=TeamItemResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    workspace_id: str,
    payload: TeamUpsertRequest,
    context: AuthContext = Depends(require_permission("team.write")),
    db: Session = Depends(get_db_session),
) -> TeamItemResponse:
    workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id))
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

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
            role="team_admin",
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
    )


@router.patch("/teams/{team_id}", response_model=TeamItemResponse)
def update_team(
    team_id: str,
    payload: TeamUpsertRequest,
    context: AuthContext = Depends(require_permission("team.write")),
    db: Session = Depends(get_db_session),
) -> TeamItemResponse:
    team = db.scalar(select(Team).options(joinedload(Team.workspace), selectinload(Team.members)).where(Team.id == team_id))
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")

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
    )


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: str,
    context: AuthContext = Depends(require_permission("team.write")),
    db: Session = Depends(get_db_session),
) -> None:
    team = db.scalar(select(Team).where(Team.id == team_id))
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.team.delete",
        entity_kind="team",
        entity_id=team.id,
        summary=f"Deleted team {team.name}",
    )
    db.delete(team)
    db.commit()


@router.get("/teams/{team_id}/members", response_model=list[AdminUserItemResponse])
def list_team_members(
    team_id: str,
    context: AuthContext = Depends(require_permission("team.read")),
    db: Session = Depends(get_db_session),
) -> list[AdminUserItemResponse]:
    team = db.scalar(select(Team).options(selectinload(Team.members)).where(Team.id == team_id))
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")
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
    context: AuthContext = Depends(require_permission("team.write")),
    db: Session = Depends(get_db_session),
) -> list[AdminUserItemResponse]:
    team = db.scalar(select(Team).options(selectinload(Team.members)).where(Team.id == team_id))
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found.")

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
            required_permissions=list(item.required_permissions or []),
            allowed_workspace_keys=list(item.allowed_workspace_keys or []),
            allowed_group_slugs=list(item.allowed_group_slugs or []),
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
        policy.required_permissions = update.required_permissions
        policy.allowed_workspace_keys = update.allowed_workspace_keys
        policy.allowed_group_slugs = update.allowed_group_slugs
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
