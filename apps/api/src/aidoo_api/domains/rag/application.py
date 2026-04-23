from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import Settings, get_settings
from aidoo_api.domains.auth.access import resolve_workspace_enabled_app_ids, resolve_workspace_role
from aidoo_api.domains.auth.models import Team, TeamMember, User, Workspace
from aidoo_api.domains.docs.models import DocMeetingAccess, NativeDoc, NativeDocContainer, NativeDocUserShare
from aidoo_api.domains.meeting.models import Meeting, MeetingAttendee
from aidoo_api.domains.planner.models import PlannerEvent
from aidoo_api.domains.pms.models import Issue, IssueUserAccess, TaskList
from aidoo_api.domains.rag.access_filter import (
    build_user_rag_post_filter,
)
from aidoo_api.domains.rag.contracts import (
    RagAnswerMode,
    RagJobStatus,
    RagQueryRequest,
    RagQueryResponse,
    RagSyncLane,
)
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from aidoo_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE
from aidoo_api.domains.rag.outbox import enqueue_rag_sync_job
from aidoo_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE
from aidoo_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.runtime import (
    build_rag_query_service,
    ensure_default_collection_ready,
    get_default_embedding_dimensions,
    get_provider_bundle,
    get_rag_query_service,
    resolve_default_collection_name,
)
from aidoo_api.domains.rag.models import RagSyncJob


DOC_SOURCE_KIND_LABELS = {
    "manual": "Docs / Manual",
    "meeting_notes": "Docs / Meeting Notes",
    "app_generated": "Docs / App Generated",
}

SOURCE_KIND_DEFINITIONS = (
    {
        "source_kind": "meeting",
        "resource_type": MEETING_RESOURCE_TYPE,
        "label": "Meetings",
        "app_id": "meeting",
    },
    {
        "source_kind": "pms_issue",
        "resource_type": PMS_ISSUE_RESOURCE_TYPE,
        "label": "PMS Issues",
        "app_id": "pms",
    },
    {
        "source_kind": "planner_event",
        "resource_type": PLANNER_EVENT_RESOURCE_TYPE,
        "label": "Planner Events",
        "app_id": "planner",
    },
)

SEARCHABLE_RAG_APP_IDS = frozenset({"docs", "meeting", "pms", "planner"})


class RagUnavailableError(RuntimeError):
    pass


class RagAccessDeniedError(RuntimeError):
    pass


class RagReindexCooldownError(RuntimeError):
    pass


RAG_REINDEX_COOLDOWN = timedelta(minutes=5)


def ensure_rag_enabled(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    if not resolved.rag_enabled:
        raise RagUnavailableError("RAG is disabled.")
    return resolved


def query_workspace_rag(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    answer_mode,
    source_kinds: list[str],
    filters: dict[str, Any],
    top_k: int,
    include_binary_hits: bool,
    settings: Settings | None = None,
    query_service: RagQueryService | None = None,
) -> RagQueryResponse:
    resolved_settings = ensure_rag_enabled(settings)
    _resolve_workspace_rag_enabled_app_ids(db, workspace.id)
    visible_sources = list_workspace_rag_sources(
        db,
        workspace=workspace,
        user=user,
        settings=resolved_settings,
    )
    allowed_source_kinds = {item["source_kind"] for item in visible_sources}
    requested_source_kinds = list(dict.fromkeys(source_kinds))
    if requested_source_kinds:
        effective_source_kinds = [
            source_kind for source_kind in requested_source_kinds if source_kind in allowed_source_kinds
        ]
    else:
        effective_source_kinds = sorted(allowed_source_kinds)
    if not effective_source_kinds:
        return _empty_query_response(
            query=query,
            answer_mode=answer_mode,
            reason="no_accessible_sources",
            requested_source_kinds=requested_source_kinds,
        )
    try:
        providers = get_provider_bundle() if settings is None else None
        service = (
            query_service
            or (get_rag_query_service() if settings is None else build_rag_query_service(resolved_settings))
        )
        ensure_default_collection_ready(
            resolved_settings,
            providers=providers,
            dense_dimensions=get_default_embedding_dimensions() if settings is None else None,
        )
    except Exception as error:
        raise RagUnavailableError(f"RAG runtime is unavailable: {error}") from error
    effective_filters = _resolve_query_filters(
        filters=filters,
        include_binary_hits=include_binary_hits,
    )
    request = RagQueryRequest(
        collection=resolve_default_collection_name(resolved_settings),
        workspace_id=workspace.id,
        query=query,
        answer_mode=answer_mode,
        source_kinds=effective_source_kinds,
        filters=effective_filters,
        top_k=top_k,
        include_binary_hits=include_binary_hits,
    )
    post_filter = build_user_rag_post_filter(db, user=user)
    return service.query(request, post_filter=post_filter)


def list_workspace_rag_sources(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    settings: Settings | None = None,
) -> list[dict[str, str]]:
    ensure_rag_enabled(settings)
    enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(db, workspace.id)
    sources: list[dict[str, str]] = []
    if "docs" in enabled_app_ids:
        for source_kind in _visible_doc_source_kinds(db, workspace=workspace, user=user):
            sources.append(
                {
                    "source_kind": source_kind,
                    "resource_type": NATIVE_DOC_RESOURCE_TYPE,
                    "label": DOC_SOURCE_KIND_LABELS.get(
                        source_kind,
                        f"Docs / {source_kind.replace('_', ' ').title()}",
                    ),
                    "app_id": "docs",
                }
            )

    for definition in SOURCE_KIND_DEFINITIONS:
        if definition["app_id"] not in enabled_app_ids:
            continue
        if not _user_has_accessible_source(
            db,
            workspace=workspace,
            user=user,
            resource_type=definition["resource_type"],
        ):
            continue
        sources.append(dict(definition))
    return sources


def enqueue_workspace_rag_reindex(
    db: Session,
    *,
    workspace: Workspace,
    settings: Settings | None = None,
) -> dict[str, Any]:
    resolved_settings = ensure_rag_enabled(settings)
    enabled_app_ids = _resolve_workspace_rag_enabled_app_ids(db, workspace.id)
    _ensure_workspace_reindex_available(db, workspace=workspace)
    try:
        ensure_default_collection_ready(
            resolved_settings,
            providers=get_provider_bundle() if settings is None else None,
            dense_dimensions=get_default_embedding_dimensions() if settings is None else None,
        )
    except Exception as error:
        raise RagUnavailableError(f"RAG runtime is unavailable: {error}") from error
    resource_counts = {
        NATIVE_DOC_RESOURCE_TYPE: 0,
        MEETING_RESOURCE_TYPE: 0,
        PMS_ISSUE_RESOURCE_TYPE: 0,
        PLANNER_EVENT_RESOURCE_TYPE: 0,
    }
    if "docs" in enabled_app_ids:
        resource_counts[NATIVE_DOC_RESOURCE_TYPE] = _enqueue_ids(
            db,
            workspace=workspace,
            resource_type=NATIVE_DOC_RESOURCE_TYPE,
            resource_ids=db.scalars(
                select(NativeDoc.id).where(
                    NativeDoc.workspace_id == workspace.id,
                    NativeDoc.trashed_at.is_(None),
                )
            ),
        )
    if "meeting" in enabled_app_ids:
        resource_counts[MEETING_RESOURCE_TYPE] = _enqueue_ids(
            db,
            workspace=workspace,
            resource_type=MEETING_RESOURCE_TYPE,
            resource_ids=db.scalars(select(Meeting.id).where(Meeting.workspace_id == workspace.id)),
        )
    if "pms" in enabled_app_ids:
        resource_counts[PMS_ISSUE_RESOURCE_TYPE] = _enqueue_ids(
            db,
            workspace=workspace,
            resource_type=PMS_ISSUE_RESOURCE_TYPE,
            resource_ids=db.scalars(
                select(Issue.id)
                .join(TaskList, Issue.list_id == TaskList.id)
                .join(Team, TaskList.team_id == Team.id)
                .where(Team.workspace_id == workspace.id)
            ),
        )
    if "planner" in enabled_app_ids:
        resource_counts[PLANNER_EVENT_RESOURCE_TYPE] = _enqueue_ids(
            db,
            workspace=workspace,
            resource_type=PLANNER_EVENT_RESOURCE_TYPE,
            resource_ids=db.scalars(
                select(PlannerEvent.id).where(PlannerEvent.workspace_id == workspace.id)
            ),
        )
    return {
        "lane": RagSyncLane.BACKFILL.value,
        "queued_count": sum(resource_counts.values()),
        "resource_counts": resource_counts,
    }


def _resolve_workspace_rag_enabled_app_ids(db: Session, workspace_id: str) -> set[str]:
    enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace_id))
    if "ai" not in enabled_app_ids:
        raise RagAccessDeniedError("Workspace RAG is not enabled for this workspace.")
    if not SEARCHABLE_RAG_APP_IDS.intersection(enabled_app_ids):
        raise RagAccessDeniedError("Workspace RAG is not enabled for this workspace.")
    return enabled_app_ids


def _visible_doc_source_kinds(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> list[str]:
    workspace_admin = resolve_workspace_role(db, user, workspace.id) == "admin"
    now = _utcnow()
    accessible_doc_ids: list[Any] = [
        select(NativeDoc.id.label("doc_id")).where(
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.trashed_at.is_(None),
            NativeDoc.owner_id == user.id,
        ),
        select(NativeDocUserShare.doc_id.label("doc_id"))
        .join(NativeDoc, NativeDoc.id == NativeDocUserShare.doc_id)
        .where(
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.trashed_at.is_(None),
            NativeDocUserShare.user_id == user.id,
        ),
        select(DocMeetingAccess.doc_id.label("doc_id"))
        .join(NativeDoc, NativeDoc.id == DocMeetingAccess.doc_id)
        .where(
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.trashed_at.is_(None),
            DocMeetingAccess.user_id == user.id,
            DocMeetingAccess.revoked_at.is_(None),
            or_(
                DocMeetingAccess.expires_at.is_(None),
                DocMeetingAccess.expires_at > now,
            ),
        ),
    ]
    container_predicates = [
        and_(
            NativeDocContainer.container_app == "docs",
            NativeDocContainer.container_type == "workspace_sidebar",
            NativeDocContainer.container_id == workspace.id,
        )
    ]
    accessible_team_ids = _accessible_team_ids_query(
        workspace=workspace,
        user=user,
        workspace_admin=workspace_admin,
    )
    if accessible_team_ids is not None:
        container_predicates.append(
            and_(
                NativeDocContainer.container_app == "pms",
                NativeDocContainer.container_type == "space",
                NativeDocContainer.container_id.in_(accessible_team_ids),
            )
        )
    accessible_doc_ids.append(
        select(NativeDocContainer.doc_id.label("doc_id"))
        .join(NativeDoc, NativeDoc.id == NativeDocContainer.doc_id)
        .where(
            NativeDoc.workspace_id == workspace.id,
            NativeDoc.trashed_at.is_(None),
            or_(*container_predicates),
        )
    )
    accessible_doc_ids_subquery = accessible_doc_ids[0].union(*accessible_doc_ids[1:]).subquery()
    return sorted(
        str(source_kind)
        for source_kind in db.scalars(
            select(NativeDoc.source_kind)
            .where(
                NativeDoc.id.in_(select(accessible_doc_ids_subquery.c.doc_id)),
                NativeDoc.source_kind.is_not(None),
            )
            .distinct()
        ).all()
        if source_kind
    )


def _user_has_accessible_source(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    resource_type: str,
) -> bool:
    if resource_type == MEETING_RESOURCE_TYPE:
        return (
            db.scalar(
                select(Meeting.id)
                .where(
                    Meeting.workspace_id == workspace.id,
                    or_(
                        Meeting.organizer_id == user.id,
                        Meeting.id.in_(
                            select(MeetingAttendee.meeting_id).where(
                                MeetingAttendee.user_id == user.id
                            )
                        ),
                    ),
                )
                .limit(1)
            )
            is not None
        )
    if resource_type == PLANNER_EVENT_RESOURCE_TYPE:
        return (
            db.scalar(
                select(PlannerEvent.id)
                .where(
                    PlannerEvent.workspace_id == workspace.id,
                    or_(
                        PlannerEvent.owner_id == user.id,
                        PlannerEvent.visibility == "public",
                    ),
                )
                .limit(1)
            )
            is not None
        )
    if resource_type == PMS_ISSUE_RESOURCE_TYPE:
        workspace_admin = resolve_workspace_role(db, user, workspace.id) == "admin"
        team_query = (
            select(Issue.id)
            .join(TaskList, Issue.list_id == TaskList.id)
            .join(Team, TaskList.team_id == Team.id)
            .where(
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if not workspace_admin:
            team_query = team_query.join(TeamMember, TeamMember.team_id == Team.id).where(
                TeamMember.user_id == user.id
            )
        if db.scalar(team_query.limit(1)) is not None:
            return True

        now = _utcnow()
        grant_query = (
            select(IssueUserAccess.issue_id)
            .join(Issue, Issue.id == IssueUserAccess.issue_id)
            .join(TaskList, Issue.list_id == TaskList.id)
            .join(Team, TaskList.team_id == Team.id)
            .where(
                Team.workspace_id == workspace.id,
                IssueUserAccess.user_id == user.id,
                IssueUserAccess.revoked_at.is_(None),
                or_(
                    IssueUserAccess.expires_at.is_(None),
                    IssueUserAccess.expires_at > now,
                ),
            )
            .limit(1)
        )
        return db.scalar(grant_query) is not None
    return False


def _enqueue_ids(
    db: Session,
    *,
    workspace: Workspace,
    resource_type: str,
    resource_ids: Iterable[str],
) -> int:
    count = 0
    for resource_id in resource_ids:
        enqueue_rag_sync_job(
            db,
            workspace_id=workspace.id,
            resource_type=resource_type,
            resource_id=resource_id,
            lane=RagSyncLane.BACKFILL,
        )
        count += 1
    return count


def _empty_query_response(
    *,
    query: str,
    answer_mode: RagAnswerMode,
    reason: str,
    requested_source_kinds: list[str],
) -> RagQueryResponse:
    return RagQueryResponse(
        query=query,
        answer_mode=answer_mode,
        query_profile={
            "vector_requested_top_k": 0,
            "vector_hit_count": 0,
            "post_filtered_hit_count": 0,
            "returned_hit_count": 0,
            "rerank_applied": False,
            "rerank_degraded": False,
            "post_filter_applied": True,
            "grounded_answer_degraded": False,
            "reason": reason,
            "requested_source_kinds": requested_source_kinds,
        },
    )


def _resolve_query_filters(
    *,
    filters: dict[str, Any],
    include_binary_hits: bool,
) -> dict[str, Any]:
    effective_filters = dict(filters)
    if not include_binary_hits and "content_modality" not in effective_filters:
        effective_filters["content_modality"] = "text"
    return effective_filters


def _ensure_workspace_reindex_available(
    db: Session,
    *,
    workspace: Workspace,
) -> None:
    cutoff = _utcnow() - RAG_REINDEX_COOLDOWN
    existing = db.scalar(
        select(RagSyncJob.id)
        .where(
            RagSyncJob.workspace_id == workspace.id,
            RagSyncJob.lane == RagSyncLane.BACKFILL.value,
            RagSyncJob.created_at >= cutoff,
            RagSyncJob.status.in_(
                [
                    RagJobStatus.PENDING.value,
                    RagJobStatus.PROCESSING.value,
                    RagJobStatus.SUCCEEDED.value,
                ]
            ),
        )
        .limit(1)
    )
    if existing is not None:
        raise RagReindexCooldownError(
            "Workspace RAG reindex was triggered recently. Wait a few minutes before retrying."
        )


def _accessible_team_ids_query(
    *,
    workspace: Workspace,
    user: User,
    workspace_admin: bool,
):
    query = select(Team.id).where(
        Team.workspace_id == workspace.id,
        Team.active.is_(True),
        Team.trashed_at.is_(None),
    )
    if workspace_admin:
        return query
    return query.join(TeamMember, TeamMember.team_id == Team.id).where(TeamMember.user_id == user.id)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
