from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import bindparam, func, or_, select
from sqlalchemy.orm import Session, aliased, load_only

from open_alm_api.domains.ai_artifacts.models import (
    AiArtifact,
    AiArtifactQuery,
    AiArtifactSource,
)
from open_alm_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.conversations.models import Conversation, ConversationTurn


LEGACY_ISSUE_REPORT_TITLE = "과거차 문제점 근거 기반 보고서"
LEGACY_ISSUE_REPORT_APP_ID = "legacy-issues"
LegacyIssueReportView = Literal["mine", "shared"]
_SYNTHETIC_SQL_SOURCE_KIND = "sql_query"


@dataclass(frozen=True)
class LegacyIssueAssistantReport:
    report_id: str
    report_number: str
    conversation_id: str | None
    turn_id: str | None
    conversation_title: str | None
    question: str
    title: str
    preview_content: str
    completed_at: datetime
    owner_user_id: str | None
    owner_name: str | None
    visibility: str
    query_count: int
    source_count: int


@dataclass(frozen=True)
class LegacyIssueAssistantReportPage:
    items: tuple[LegacyIssueAssistantReport, ...]
    total: int


def list_legacy_issue_reports(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
    view: LegacyIssueReportView,
    limit: int,
    offset: int,
) -> LegacyIssueAssistantReportPage:
    projection = _report_projection(view=view).subquery("legacy_issue_reports")
    params = {
        "workspace_id": workspace_id,
        "user_id": user_id,
    }
    total = db.scalar(select(func.count()).select_from(projection), params) or 0
    rows = db.execute(
        select(projection)
        .order_by(
            projection.c.completed_at.desc(),
            projection.c.report_id.asc(),
        )
        .limit(limit)
        .offset(offset),
        params,
    ).mappings()
    return LegacyIssueAssistantReportPage(
        items=tuple(_report_from_row(row) for row in rows),
        total=int(total),
    )


def list_legacy_issue_assistant_reports(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
    limit: int,
    offset: int,
) -> LegacyIssueAssistantReportPage:
    """Compatibility projection for the former assistant report-history route."""

    return list_legacy_issue_reports(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        view="mine",
        limit=limit,
        offset=offset,
    )


def get_visible_legacy_issue_report(
    db: Session,
    *,
    identifier: str,
    workspace_id: str,
    user_id: str,
    eager: bool = False,
) -> AiArtifact | None:
    artifact = AiArtifactRepository(db).get_visible(
        identifier,
        workspace_id=workspace_id,
        user_id=user_id,
        eager=eager,
    )
    if artifact is None or not _is_completed_legacy_issue_report(artifact):
        return None
    return artifact


def get_legacy_issue_report_query(
    db: Session,
    *,
    artifact_id: str,
    query_id: str,
) -> AiArtifactQuery | None:
    return db.scalar(
        select(AiArtifactQuery).where(
            AiArtifactQuery.id == query_id,
            AiArtifactQuery.artifact_id == artifact_id,
        )
    )


def list_legacy_issue_report_queries(
    db: Session,
    *,
    artifact_id: str,
) -> tuple[AiArtifactQuery, ...]:
    return tuple(
        db.scalars(
            select(AiArtifactQuery)
            .options(
                load_only(
                    AiArtifactQuery.id,
                    AiArtifactQuery.ordinal,
                    AiArtifactQuery.query_kind,
                    AiArtifactQuery.title,
                    AiArtifactQuery.family_id,
                    AiArtifactQuery.query_spec_json,
                    AiArtifactQuery.statement_text,
                    AiArtifactQuery.typed_params_json,
                    AiArtifactQuery.execution_status,
                    AiArtifactQuery.error_code,
                    AiArtifactQuery.query_sha256,
                    AiArtifactQuery.result_sha256,
                    AiArtifactQuery.row_count,
                    AiArtifactQuery.duration_ms,
                    AiArtifactQuery.truncated,
                    AiArtifactQuery.payload_bytes,
                    AiArtifactQuery.exactness,
                    AiArtifactQuery.created_at,
                )
            )
            .where(AiArtifactQuery.artifact_id == artifact_id)
            .order_by(AiArtifactQuery.ordinal)
        )
    )


def list_legacy_issue_report_sources(
    db: Session,
    *,
    artifact_id: str,
) -> tuple[AiArtifactSource, ...]:
    return tuple(
        db.scalars(
            select(AiArtifactSource)
            .where(
                AiArtifactSource.artifact_id == artifact_id,
                AiArtifactSource.source_kind != _SYNTHETIC_SQL_SOURCE_KIND,
            )
            .order_by(AiArtifactSource.ordinal)
        )
    )


def legacy_issue_report_counts(
    db: Session,
    *,
    artifact_id: str,
) -> tuple[int, int]:
    query_count = db.scalar(
        select(func.count(AiArtifactQuery.id)).where(
            AiArtifactQuery.artifact_id == artifact_id
        )
    )
    source_count = db.scalar(
        select(func.count(AiArtifactSource.id)).where(
            AiArtifactSource.artifact_id == artifact_id,
            AiArtifactSource.source_kind != _SYNTHETIC_SQL_SOURCE_KIND,
        )
    )
    return int(query_count or 0), int(source_count or 0)


def report_question(db: Session, artifact: AiArtifact) -> str:
    payload = artifact.payload_json
    if isinstance(payload, dict):
        request = payload.get("request")
        if isinstance(request, dict):
            text = request.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    if artifact.conversation_turn_id:
        assistant_turn = db.get(ConversationTurn, artifact.conversation_turn_id)
        if assistant_turn is not None:
            preceding_question = db.scalar(
                select(ConversationTurn.content)
                .where(
                    ConversationTurn.conversation_id == assistant_turn.conversation_id,
                    ConversationTurn.role == "user",
                    ConversationTurn.seq < assistant_turn.seq,
                )
                .order_by(ConversationTurn.seq.desc())
                .limit(1)
            )
            if preceding_question:
                return preceding_question
    return ""


def report_owner(db: Session, artifact: AiArtifact) -> User | None:
    return db.get(User, artifact.owner_user_id) if artifact.owner_user_id else None


def _report_from_row(row) -> LegacyIssueAssistantReport:
    return LegacyIssueAssistantReport(
        report_id=row["report_id"],
        report_number=row["report_number"],
        conversation_id=row["conversation_id"],
        turn_id=row["turn_id"],
        conversation_title=row["conversation_title"],
        question=row["question"] or "",
        title=row["title"],
        preview_content=row["preview_content"],
        completed_at=row["completed_at"],
        owner_user_id=row["owner_user_id"],
        owner_name=row["owner_name"],
        visibility=row["visibility"],
        query_count=int(row["query_count"] or 0),
        source_count=int(row["source_count"] or 0),
    )


def _is_completed_legacy_issue_report(artifact: AiArtifact) -> bool:
    return (
        artifact.app_id == LEGACY_ISSUE_REPORT_APP_ID
        and artifact.artifact_type == "report"
        and artifact.status == "completed"
        and bool(artifact.content_text)
    )


def _report_projection(*, view: LegacyIssueReportView):
    assistant_turn = aliased(ConversationTurn, name="assistant_turn")
    user_turn = aliased(ConversationTurn, name="preceding_user_turn")
    owner = aliased(User, name="report_owner")
    preceding_question = (
        select(user_turn.content)
        .where(
            user_turn.conversation_id == assistant_turn.conversation_id,
            user_turn.role == "user",
            user_turn.seq < assistant_turn.seq,
        )
        .order_by(user_turn.seq.desc())
        .limit(1)
        .correlate(assistant_turn)
        .scalar_subquery()
    )
    stored_question = AiArtifact.payload_json["request"]["text"].as_string()
    query_count = (
        select(func.count(AiArtifactQuery.id))
        .where(AiArtifactQuery.artifact_id == AiArtifact.id)
        .correlate(AiArtifact)
        .scalar_subquery()
    )
    source_count = (
        select(func.count(AiArtifactSource.id))
        .where(
            AiArtifactSource.artifact_id == AiArtifact.id,
            AiArtifactSource.source_kind != _SYNTHETIC_SQL_SOURCE_KIND,
        )
        .correlate(AiArtifact)
        .scalar_subquery()
    )
    visibility_predicate = (
        AiArtifact.owner_user_id == bindparam("user_id")
        if view == "mine"
        else (
            (AiArtifact.visibility == "workspace")
            & (
                or_(
                    AiArtifact.owner_user_id.is_(None),
                    AiArtifact.owner_user_id != bindparam("user_id"),
                )
            )
        )
    )

    return (
        select(
            AiArtifact.id.label("report_id"),
            AiArtifact.artifact_number.label("report_number"),
            AiArtifact.conversation_id.label("conversation_id"),
            AiArtifact.conversation_turn_id.label("turn_id"),
            Conversation.title.label("conversation_title"),
            func.coalesce(
                func.nullif(stored_question, ""),
                preceding_question,
                "",
            ).label("question"),
            AiArtifact.title.label("title"),
            func.substr(AiArtifact.content_text, 1, 1000).label("preview_content"),
            func.coalesce(
                AiArtifact.completed_at,
                AiArtifact.created_at,
            ).label("completed_at"),
            AiArtifact.owner_user_id.label("owner_user_id"),
            owner.display_name.label("owner_name"),
            AiArtifact.visibility.label("visibility"),
            query_count.label("query_count"),
            source_count.label("source_count"),
        )
        .select_from(AiArtifact)
        .outerjoin(
            Conversation,
            Conversation.id == AiArtifact.conversation_id,
        )
        .outerjoin(
            assistant_turn,
            assistant_turn.id == AiArtifact.conversation_turn_id,
        )
        .outerjoin(owner, owner.id == AiArtifact.owner_user_id)
        .where(
            AiArtifact.workspace_id == bindparam("workspace_id"),
            visibility_predicate,
            AiArtifact.app_id == LEGACY_ISSUE_REPORT_APP_ID,
            AiArtifact.artifact_type == "report",
            AiArtifact.status == "completed",
            func.nullif(AiArtifact.content_text, "").is_not(None),
        )
    )


__all__ = [
    "LEGACY_ISSUE_REPORT_APP_ID",
    "LEGACY_ISSUE_REPORT_TITLE",
    "LegacyIssueAssistantReport",
    "LegacyIssueAssistantReportPage",
    "LegacyIssueReportView",
    "get_legacy_issue_report_query",
    "get_visible_legacy_issue_report",
    "list_legacy_issue_assistant_reports",
    "legacy_issue_report_counts",
    "list_legacy_issue_report_queries",
    "list_legacy_issue_report_sources",
    "list_legacy_issue_reports",
    "report_owner",
    "report_question",
]
