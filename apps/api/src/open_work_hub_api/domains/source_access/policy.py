from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.access import get_current_workspace, resolve_workspace_role
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.workspace_app_gate import (
    is_app_enabled_for_user_context,
    is_company_app_enabled_for_user_context,
)
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclBranch,
    KeywordAclClause,
    KeywordAclFilter,
    keyword_acl_clause,
)
from open_work_hub_api.domains.source_access.access_scope import AccessScopePolicy
from open_work_hub_api.domains.source_access.default_adapters import (
    ensure_builtin_source_access_adapters_registered,
)
from open_work_hub_api.domains.source_access.registry import (
    get_source_access_adapter,
    get_source_access_adapters,
)
from open_work_hub_api.domains.source_access.resource_types import (
    MEETING_RESOURCE_TYPE,
    NATIVE_DOC_RESOURCE_TYPE,
    PLANNER_EVENT_RESOURCE_TYPE,
    PMS_TASK_RESOURCE_TYPE,
)


@dataclass(frozen=True)
class SourceAclPolicy:
    db: Session
    workspace: Workspace | None
    user: User
    workspace_role: str | None
    execution_scope_kind: str = "workspace"

    @classmethod
    def for_workspace(
        cls,
        db: Session,
        *,
        workspace: Workspace,
        user: User,
    ) -> SourceAclPolicy:
        return cls(
            db=db,
            workspace=workspace,
            user=user,
            workspace_role=resolve_workspace_role(db, user, workspace.id),
            execution_scope_kind="workspace",
        )

    @classmethod
    def for_company(cls, db: Session, *, user: User) -> SourceAclPolicy:
        """Build an authenticated company caller without inventing a workspace."""

        return cls(
            db=db,
            workspace=None,
            user=user,
            workspace_role=None,
            execution_scope_kind="company",
        )

    @classmethod
    def for_workspace_id(
        cls,
        db: Session,
        *,
        workspace_id: str,
        user: User,
    ) -> SourceAclPolicy:
        workspace = db.scalar(
            select(Workspace).where(Workspace.id == workspace_id, Workspace.active.is_(True))
        )
        if workspace is None:
            raise ValueError(f"Workspace not found: {workspace_id}")
        return cls.for_workspace(db, workspace=workspace, user=user)

    def can_read_resource(self, resource_type: str, resource_id: str) -> bool:
        ensure_builtin_source_access_adapters_registered()
        adapter = get_source_access_adapter(resource_type)
        current = self._authorized_policy(resource_type)
        return (
            adapter is not None
            and current is not None
            and adapter.can_read_resource(
                current, resource_type=resource_type, resource_id=resource_id
            )
        )

    def can_read_rag_resource(self, resource_type: str, resource_id: str) -> bool:
        ensure_builtin_source_access_adapters_registered()
        adapter = get_source_access_adapter(resource_type)
        current = self._authorized_policy(resource_type)
        if adapter is None or current is None:
            return False
        return adapter.can_read_rag_resource(
            current, resource_type=resource_type, resource_id=resource_id
        )

    def authorize_many_rag_resources(
        self,
        resources: Iterable[tuple[str, str]],
    ) -> set[tuple[str, str]]:
        return self.authorize_many_resources(resources, rag=True)

    def authorize_many_resources(
        self,
        resources: Iterable[tuple[str, str]],
        *,
        rag: bool = False,
    ) -> set[tuple[str, str]]:
        """Authorize grouped candidates; adapters may replace the safe fallback."""

        ensure_builtin_source_access_adapters_registered()
        ids_by_type: dict[str, list[str]] = defaultdict(list)
        for resource_type, resource_id in resources:
            normalized_type = str(resource_type or "").strip()
            normalized_id = str(resource_id or "").strip()
            if (
                normalized_type
                and normalized_id
                and normalized_id not in ids_by_type[normalized_type]
            ):
                ids_by_type[normalized_type].append(normalized_id)

        allowed: set[tuple[str, str]] = set()
        for resource_type, resource_ids in ids_by_type.items():
            adapter = get_source_access_adapter(resource_type)
            current = self._authorized_policy(resource_type)
            if adapter is None or current is None:
                continue
            authorize_many = getattr(
                adapter,
                "authorize_many_rag_resources" if rag else "authorize_many_resources",
                None,
            )
            if callable(authorize_many):
                allowed_ids = authorize_many(
                    current,
                    resource_type=resource_type,
                    resource_ids=tuple(resource_ids),
                )
            else:
                allowed_ids = {
                    resource_id
                    for resource_id in resource_ids
                    if (
                        adapter.can_read_rag_resource(
                            current,
                            resource_type=resource_type,
                            resource_id=resource_id,
                        )
                        if rag
                        else adapter.can_read_resource(
                            current,
                            resource_type=resource_type,
                            resource_id=resource_id,
                        )
                    )
                }
            allowed.update(
                (resource_type, resource_id)
                for resource_id in set(allowed_ids).intersection(resource_ids)
            )
        return allowed

    def _authorized_policy(self, resource_type: str) -> SourceAclPolicy | None:
        """Recheck execution before dispatch; a saved policy is never a grant."""
        adapter = get_source_access_adapter(resource_type)
        app_id = getattr(adapter, "app_id", None)
        if not app_id or not self._adapter_allows_execution_scope(resource_type):
            return None
        if self.execution_scope_kind == "workspace":
            if self.workspace is None:
                return None
            role = resolve_workspace_role(self.db, self.user, self.workspace.id)
            if role is None or not is_app_enabled_for_user_context(
                self.db,
                app_id=app_id,
                user_id=self.user.id,
                workspace_id=self.workspace.id,
            ):
                return None
            return replace(self, workspace_role=role)
        if self.execution_scope_kind != "company" or self.workspace is not None:
            return None
        if not is_company_app_enabled_for_user_context(
            self.db,
            app_id=app_id,
            user_id=self.user.id,
        ):
            return None
        return self

    def _adapter_allows_execution_scope(self, resource_type: str) -> bool:
        if self.execution_scope_kind == "workspace":
            return True
        from open_work_hub_api.domains.retrieval.default_partition_adapters import (
            ensure_retrieval_partition_adapters_registered,
        )
        from open_work_hub_api.domains.retrieval.partition_adapter_registry import (
            get_retrieval_partition_adapter_for_resource,
        )

        ensure_retrieval_partition_adapters_registered()
        partition_adapter = get_retrieval_partition_adapter_for_resource(resource_type)
        return bool(
            partition_adapter is not None
            and self.execution_scope_kind in partition_adapter.allowed_candidate_scopes
        )

    def build_rag_post_filter(self) -> Callable[[Any], bool]:
        def _filter(hit: Any) -> bool:
            projection = hit.projection
            if self.workspace is None or projection.workspace_id != self.workspace.id:
                return False
            return self.can_read_rag_resource(
                projection.resource_type,
                projection.resource_id,
            )

        return _filter

    def build_keyword_acl_filter(self) -> KeywordAclFilter:
        ensure_builtin_source_access_adapters_registered()
        branches: list[KeywordAclBranch] = []
        for adapter in get_source_access_adapters():
            current = next(
                (
                    policy
                    for resource_type in adapter.resource_types
                    if (policy := self._authorized_policy(resource_type)) is not None
                ),
                None,
            )
            if current is not None:
                branches.extend(adapter.keyword_acl_branches(current))
        return KeywordAclFilter(branches=tuple(branches))

    def restrict_visible_native_docs(self, base):
        from open_work_hub_api.domains.docs import source_access

        ensure_builtin_source_access_adapters_registered()
        current = self._authorized_policy(NATIVE_DOC_RESOURCE_TYPE)
        return (
            base.where(false())
            if current is None
            else source_access.restrict_visible_native_docs(current, base)
        )

    def visible_native_doc_source_kinds(self) -> list[str]:
        from open_work_hub_api.domains.docs import source_access

        ensure_builtin_source_access_adapters_registered()
        current = self._authorized_policy(NATIVE_DOC_RESOURCE_TYPE)
        return [] if current is None else source_access.visible_native_doc_source_kinds(current)

    def visible_rag_native_doc_source_kinds(self) -> list[str]:
        from open_work_hub_api.domains.docs import source_access

        ensure_builtin_source_access_adapters_registered()
        current = self._authorized_policy(NATIVE_DOC_RESOURCE_TYPE)
        return [] if current is None else source_access.visible_rag_native_doc_source_kinds(current)

    def has_accessible_source(self, resource_type: str) -> bool:
        ensure_builtin_source_access_adapters_registered()
        adapter = get_source_access_adapter(resource_type)
        current = self._authorized_policy(resource_type)
        return (
            adapter is not None
            and current is not None
            and adapter.has_accessible_source(current, resource_type=resource_type)
        )

    def can_read_native_doc(self, doc_id: str) -> bool:
        return self.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, doc_id)

    def can_read_official_native_doc(self, doc_id: str) -> bool:
        return self.can_read_rag_resource(NATIVE_DOC_RESOURCE_TYPE, doc_id)

    def can_read_pms_task(self, task_id: str) -> bool:
        return self.can_read_resource(PMS_TASK_RESOURCE_TYPE, task_id)

    def can_read_meeting(self, meeting_id: str) -> bool:
        return self.can_read_resource(MEETING_RESOURCE_TYPE, meeting_id)

    def can_read_planner_event(self, event_id: str) -> bool:
        return self.can_read_resource(PLANNER_EVENT_RESOURCE_TYPE, event_id)

    def _keyword_entity_branch(
        self, entity_type: str, clauses: list[KeywordAclClause]
    ) -> KeywordAclBranch:
        return KeywordAclBranch(entity_type=entity_type, clauses=tuple(clauses))

    def _keyword_acl_clause(
        self,
        field: str,
        value: str | list[str] | tuple[str, ...],
    ) -> KeywordAclClause:
        return keyword_acl_clause(field, value)

    def _access_scope_policy(self) -> AccessScopePolicy:
        return AccessScopePolicy(
            db=self.db,
            workspace_id=self.workspace.id,
            workspace_role=self.workspace_role,
            user_id=self.user.id,
        )

    def _active_team_ids_query(self):
        return self._access_scope_policy().active_team_ids_query()

    def _accessible_team_ids(self) -> list[str]:
        return self._access_scope_policy().accessible_team_ids()

    def can_access_scope(self, scope_kind: str | None, scope_id: str | None) -> bool:
        return self._access_scope_policy().can_access(scope_kind, scope_id)

    def _access_scope_predicate(self, scope_kind_column, scope_id_column):
        return self._access_scope_policy().predicate(scope_kind_column, scope_id_column)

    def _native_doc_read_predicate(self):
        from open_work_hub_api.domains.docs import source_access

        return source_access.native_doc_read_predicate(self)

    def _meeting_read_predicate(self):
        from open_work_hub_api.domains.meeting import source_access

        return source_access.meeting_read_predicate(self)

    def _planner_event_read_predicate(self):
        from open_work_hub_api.domains.planner import source_access

        return source_access.planner_event_read_predicate(self)

    def _accessible_pms_task_query(self):
        from open_work_hub_api.domains.pms import source_access

        return source_access.accessible_pms_task_query(self)

    def _has_accessible_meeting(self) -> bool:
        from open_work_hub_api.domains.meeting import source_access

        return source_access.has_accessible_meeting(self)

    def _has_accessible_planner_event(self) -> bool:
        from open_work_hub_api.domains.planner import source_access

        return source_access.has_accessible_planner_event(self)

    def _has_accessible_pms_task(self) -> bool:
        from open_work_hub_api.domains.pms import source_access

        return source_access.has_accessible_pms_task(self)


def can_read_resource(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    policy = _policy_for_workspace_id(db, workspace_id=workspace_id, user=user)
    return policy is not None and policy.can_read_resource(resource_type, resource_id)


def can_read_native_doc(db: Session, *, user: User, doc_id: str) -> bool:
    from open_work_hub_api.domains.docs import source_access

    doc_workspace_id = source_access.resolve_native_doc_workspace_id(db, doc_id=doc_id)
    return _can_read_in_resource_workspace(
        db,
        user=user,
        workspace_id=doc_workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc_id,
    )


def can_read_pms_task(db: Session, *, user: User, task_id: str) -> bool:
    from open_work_hub_api.domains.pms import source_access

    workspace_id = source_access.resolve_pms_task_workspace_id(db, task_id=task_id)
    return _can_read_in_resource_workspace(
        db,
        user=user,
        workspace_id=workspace_id,
        resource_type=PMS_TASK_RESOURCE_TYPE,
        resource_id=task_id,
    )


def can_read_meeting(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    meeting_id: str,
) -> bool:
    return can_read_resource(
        db,
        user=user,
        workspace_id=workspace_id,
        resource_type=MEETING_RESOURCE_TYPE,
        resource_id=meeting_id,
    )


def can_read_planner_event(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    event_id: str,
) -> bool:
    return can_read_resource(
        db,
        user=user,
        workspace_id=workspace_id,
        resource_type=PLANNER_EVENT_RESOURCE_TYPE,
        resource_id=event_id,
    )


def _can_read_in_resource_workspace(
    db: Session,
    *,
    user: User,
    workspace_id: str | None,
    resource_type: str,
    resource_id: str,
) -> bool:
    if workspace_id is None:
        return False
    current_workspace = get_current_workspace(db)
    if current_workspace is not None and current_workspace.id != workspace_id:
        return False
    return can_read_resource(
        db,
        user=user,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def _policy_for_workspace_id(
    db: Session,
    *,
    workspace_id: str,
    user: User,
) -> SourceAclPolicy | None:
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.active.is_(True))
    )
    if workspace is None:
        return None
    return SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
