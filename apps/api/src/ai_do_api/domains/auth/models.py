from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class OrgUnit(Base):
    __tablename__ = "org_units"
    __table_args__ = (
        CheckConstraint("unit_type IN ('group', 'division')", name="ck_org_units_unit_type"),
        UniqueConstraint(
            "hr_source_system",
            "hr_domain_num",
            "hr_depart_num",
            name="uq_org_units_hr_source_identity",
        ),
        UniqueConstraint(
            "hr_source_system",
            "hr_domain_num",
            "hr_org_code",
            name="uq_org_units_hr_org_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    unit_type: Mapped[str] = mapped_column(
        String(24), default="division", nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"), nullable=True, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    hr_source_system: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    hr_domain_num: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hr_depart_num: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hr_org_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    hr_parent_org_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    hr_org_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_org_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hr_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
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
    teams: Mapped[list["Team"]] = relationship(back_populates="org_unit")


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
    __table_args__ = (
        CheckConstraint(
            "auth_provider IN ('local', 'groupware')",
            name="ck_users_auth_provider",
        ),
        UniqueConstraint(
            "hr_source_system",
            "hr_domain_num",
            "hr_user_num",
            name="uq_users_hr_source_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    login_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(
        String(32), default="local", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    login_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_preference: Mapped[str] = mapped_column(String(16), default="system")
    locale: Mapped[str] = mapped_column(String(16), default="ko-KR", nullable=False)
    time_zone: Mapped[str] = mapped_column(String(64), default="Asia/Seoul", nullable=False)
    date_format: Mapped[str] = mapped_column(String(24), default="korean", nullable=False)
    app_bar_layout: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    default_workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    primary_org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"),
        nullable=True,
        index=True,
    )
    hr_source_system: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    hr_domain_num: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hr_user_num: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hr_com_state: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    hr_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    primary_org_unit: Mapped[OrgUnit | None] = relationship(back_populates="users")
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
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user",
        foreign_keys="AuthSession.user_id",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")


class UserSystemRole(Base):
    __tablename__ = "user_system_roles"
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_system_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    user: Mapped[User] = relationship(back_populates="system_role_links")


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


class WorkspaceAppEntitlement(Base):
    __tablename__ = "workspace_app_entitlements"
    __table_args__ = (
        UniqueConstraint("workspace_id", "app_id", name="uq_workspace_app_entitlement"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    visibility_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    workspace: Mapped[Workspace] = relationship(back_populates="app_entitlements")


class PlatformAppVisibility(Base):
    __tablename__ = "platform_app_visibility"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class PlatformAppBarCategory(Base):
    __tablename__ = "platform_app_bar_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(120))
    icon_key: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    apps: Mapped[list["PlatformAppBarCategoryApp"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class PlatformAppBarCategoryApp(Base):
    __tablename__ = "platform_app_bar_category_apps"
    __table_args__ = (
        UniqueConstraint("category_id", "app_id", name="uq_platform_app_bar_category_app"),
        UniqueConstraint("app_id", name="uq_platform_app_bar_category_apps_app_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("platform_app_bar_categories.id", ondelete="CASCADE"),
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(64), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    category: Mapped[PlatformAppBarCategory] = relationship(back_populates="apps")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("workspace_id", "key", name="uq_workspace_team_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"), nullable=True, index=True
    )
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
    org_unit: Mapped[OrgUnit | None] = relationship(back_populates="teams")
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
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_user_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_kind: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    actor: Mapped[User | None] = relationship(back_populates="audit_logs")


class PlatformApiKey(Base):
    """A revocable machine credential; plaintext is only stored encrypted."""

    __tablename__ = "platform_api_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="ck_platform_api_keys_status",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_platform_api_keys_name",
        ),
        CheckConstraint(
            "substr(key_prefix, 1, 8) = 'aido_pk_'",
            name="ck_platform_api_keys_prefix",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_by_user_id IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL)",
            name="ck_platform_api_keys_revocation",
        ),
        Index(
            "ix_platform_api_keys_status_created",
            "status",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        index=True,
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_user_created", "user_id", "created_at"),
        Index("ix_auth_sessions_user_last_seen", "user_id", "last_seen_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    impersonator_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    user: Mapped[User] = relationship(
        back_populates="sessions",
        foreign_keys=[user_id],
    )
    impersonator: Mapped[User | None] = relationship(
        foreign_keys=[impersonator_user_id],
    )


class DesktopSessionLink(Base):
    __tablename__ = "desktop_session_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_session_id: Mapped[str] = mapped_column(ForeignKey("auth_sessions.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user: Mapped[User] = relationship()
    source_session: Mapped[AuthSession] = relationship()
