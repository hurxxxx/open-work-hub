from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.access import (
    resolve_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from ai_do_api.domains.auth.models import Team, User, Workspace
from ai_do_api.domains.docs.models import NativeDoc, NativeDocContainer


@dataclass(frozen=True)
class ContainerRef:
    app: str
    type: str
    id: str


@dataclass(frozen=True)
class SourceDescriptor:
    label: str
    badge: str
    deep_link: str | None = None


@dataclass(frozen=True)
class ContainerAccessProjection:
    can_view: bool
    can_edit: bool
    can_manage: bool


class DocsSourceAdapter(Protocol):
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_container: NativeDocContainer | None,
    ) -> SourceDescriptor: ...


class DocsContainerAdapter(Protocol):
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> str | None: ...

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> bool: ...

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> ContainerAccessProjection: ...


_source_adapters: dict[str, DocsSourceAdapter] = {}
_container_adapters: dict[str, DocsContainerAdapter] = {}


def register_docs_source_adapter(app_id: str, adapter: DocsSourceAdapter) -> None:
    _source_adapters[app_id] = adapter


def register_docs_container_adapter(app_id: str, adapter: DocsContainerAdapter) -> None:
    _container_adapters[app_id] = adapter


def get_docs_source_adapter(app_id: str) -> DocsSourceAdapter | None:
    return _source_adapters.get(app_id)


def get_docs_container_adapter(app_id: str) -> DocsContainerAdapter | None:
    return _container_adapters.get(app_id)


class _DocsSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_container: NativeDocContainer | None,
    ) -> SourceDescriptor:
        return SourceDescriptor(
            label="Docs",
            badge="Docs",
            deep_link=f"/w/{workspace.key}/docs/{doc.id}",
        )


class _MeetingSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_container: NativeDocContainer | None,
    ) -> SourceDescriptor:
        return SourceDescriptor(
            label="Meeting",
            badge="Meeting",
            deep_link=f"/w/{workspace.key}/meeting",
        )


class _PmsSourceAdapter:
    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_container: NativeDocContainer | None,
    ) -> SourceDescriptor:
        if primary_container is not None and primary_container.container_type == "space":
            deep_link = f"/w/{workspace.key}/pms/tool/pms-space-{primary_container.container_id}"
        else:
            deep_link = f"/w/{workspace.key}/pms"
        return SourceDescriptor(
            label="PMS",
            badge="PMS",
            deep_link=deep_link,
        )


class _GenericSourceAdapter:
    def __init__(self, app_id: str) -> None:
        self._app_id = app_id

    def describe(
        self,
        *,
        workspace: Workspace,
        doc: NativeDoc,
        primary_container: NativeDocContainer | None,
    ) -> SourceDescriptor:
        label = self._app_id.replace("_", " ").title()
        return SourceDescriptor(
            label=label,
            badge=label,
            deep_link=f"/w/{workspace.key}/docs/{doc.id}",
        )


class _DocsContainerAdapter:
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> str | None:
        if ref.type != "workspace_sidebar" or ref.id != workspace.id:
            return None
        return "Workspace Docs"

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> bool:
        if ref.type != "workspace_sidebar" or ref.id != workspace.id:
            return False
        return resolve_workspace_role(db, user, workspace.id) is not None

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> ContainerAccessProjection:
        if ref.type != "workspace_sidebar" or ref.id != workspace.id:
            return ContainerAccessProjection(False, False, False)
        role = resolve_workspace_role(db, user, workspace.id)
        return ContainerAccessProjection(
            can_view=role is not None,
            can_edit=workspace_role_allows(role, "member"),
            can_manage=workspace_role_allows(role, "admin"),
        )


class _PmsContainerAdapter:
    def label_for(
        self,
        *,
        db: Session,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> str | None:
        if ref.type != "space":
            return None
        team = db.scalar(
            select(Team).where(
                Team.id == ref.id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        return team.name if team is not None else None

    def can_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> bool:
        if ref.type != "space":
            return False
        team = db.scalar(
            select(Team).where(
                Team.id == ref.id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if team is None:
            return False
        return resolve_team_role(db, user, team) is not None

    def project_access(
        self,
        *,
        db: Session,
        user: User,
        workspace: Workspace,
        ref: ContainerRef,
    ) -> ContainerAccessProjection:
        if ref.type != "space":
            return ContainerAccessProjection(False, False, False)
        team = db.scalar(
            select(Team).where(
                Team.id == ref.id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if team is None:
            return ContainerAccessProjection(False, False, False)
        role = resolve_team_role(db, user, team)
        return ContainerAccessProjection(
            can_view=role is not None,
            can_edit=team_role_allows(role, "member"),
            can_manage=team_role_allows(role, "admin"),
        )


def describe_source(
    *,
    workspace: Workspace,
    doc: NativeDoc,
    primary_container: NativeDocContainer | None,
) -> SourceDescriptor:
    adapter = get_docs_source_adapter(doc.source_app)
    if adapter is None:
        adapter = _GenericSourceAdapter(doc.source_app)
    return adapter.describe(workspace=workspace, doc=doc, primary_container=primary_container)


def resolve_container_label(
    *,
    db: Session,
    workspace: Workspace,
    container: NativeDocContainer | None,
) -> str:
    if container is None:
        return "Unfiled"
    adapter = get_docs_container_adapter(container.container_app)
    if adapter is None:
        return f"{container.container_app}:{container.container_type}"
    ref = ContainerRef(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
    )
    return adapter.label_for(db=db, workspace=workspace, ref=ref) or "Unfiled"


def container_access_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: ContainerRef,
) -> bool:
    adapter = get_docs_container_adapter(ref.app)
    if adapter is None:
        return False
    return adapter.can_access(db=db, user=user, workspace=workspace, ref=ref)


def project_container_access(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: ContainerRef,
) -> ContainerAccessProjection:
    adapter = get_docs_container_adapter(ref.app)
    if adapter is None:
        return ContainerAccessProjection(False, False, False)
    return adapter.project_access(db=db, user=user, workspace=workspace, ref=ref)


register_docs_source_adapter("docs", _DocsSourceAdapter())
register_docs_source_adapter("meeting", _MeetingSourceAdapter())
register_docs_source_adapter("pms", _PmsSourceAdapter())

register_docs_container_adapter("docs", _DocsContainerAdapter())
register_docs_container_adapter("pms", _PmsContainerAdapter())
