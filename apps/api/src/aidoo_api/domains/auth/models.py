from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidoo_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class OrgUnit(Base):
    __tablename__ = "org_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("org_units.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    parent: Mapped["OrgUnit | None"] = relationship(
        remote_side="OrgUnit.id",
        back_populates="children",
    )
    children: Mapped[list["OrgUnit"]] = relationship(back_populates="parent")
    users: Mapped[list["User"]] = relationship(back_populates="primary_org_unit")


class AccessGroup(Base):
    __tablename__ = "access_groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    group_kind: Mapped[str] = mapped_column(String(24), default="access", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    permissions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    members: Mapped[list["UserAccessGroup"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    workspace_bindings: Mapped[list["WorkspaceGroupBinding"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )
    system_role_links: Mapped[list["GroupSystemRole"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    user_bindings: Mapped[list["WorkspaceUserBinding"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    group_bindings: Mapped[list["WorkspaceGroupBinding"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    app_entitlements: Mapped[list["WorkspaceAppEntitlement"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="workspace",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_preference: Mapped[str] = mapped_column(String(16), default="system")
    time_zone: Mapped[str] = mapped_column(String(64), default="Asia/Seoul", nullable=False)
    primary_org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"),
        nullable=True,
        index=True,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    primary_org_unit: Mapped[OrgUnit | None] = relationship(back_populates="users")
    group_links: Mapped[list["UserAccessGroup"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    system_role_links: Mapped[list["UserSystemRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    workspace_bindings: Mapped[list["WorkspaceUserBinding"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    team_memberships: Mapped[list["TeamMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["AuthSession"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class UserAccessGroup(Base):
    __tablename__ = "user_access_groups"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_access_group"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("access_groups.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    user: Mapped[User] = relationship(back_populates="group_links")
    group: Mapped[AccessGroup] = relationship(back_populates="members")


class UserSystemRole(Base):
    __tablename__ = "user_system_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_system_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    user: Mapped[User] = relationship(back_populates="system_role_links")


class GroupSystemRole(Base):
    __tablename__ = "group_system_roles"
    __table_args__ = (UniqueConstraint("group_id", "role", name="uq_group_system_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("access_groups.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    group: Mapped[AccessGroup] = relationship(back_populates="system_role_links")


class WorkspaceUserBinding(Base):
    __tablename__ = "workspace_user_bindings"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    workspace: Mapped[Workspace] = relationship(back_populates="user_bindings")
    user: Mapped[User] = relationship(back_populates="workspace_bindings")


class WorkspaceGroupBinding(Base):
    __tablename__ = "workspace_group_bindings"
    __table_args__ = (UniqueConstraint("workspace_id", "group_id", name="uq_workspace_group"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("access_groups.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    workspace: Mapped[Workspace] = relationship(back_populates="group_bindings")
    group: Mapped[AccessGroup] = relationship(back_populates="workspace_bindings")


class WorkspaceAppEntitlement(Base):
    __tablename__ = "workspace_app_entitlements"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_workspace_app_entitlement"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    workspace: Mapped[Workspace] = relationship(back_populates="app_entitlements")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_workspace_team_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    workspace: Mapped[Workspace] = relationship(back_populates="teams")
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="team_memberships")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_kind: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    actor: Mapped[User | None] = relationship(back_populates="audit_logs")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")
