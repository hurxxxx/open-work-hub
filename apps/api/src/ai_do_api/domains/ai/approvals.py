from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from fastapi import status
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    delete,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from ai_do_api.core.db import Base
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai import approval_runtime_shadow as runtime_shadow
from ai_do_api.domains.ai.audit import log_llm_tool_approval_resolved
from ai_do_api.domains.ai.tool_contracts import AgentToolSpec, agent_tool_names
from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.auth.security import new_id

if TYPE_CHECKING:
    from ai_do_api.domains.auth.models import User, Workspace
    from ai_do_api.domains.conversations.models import Conversation


ApprovalStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "expired",
    "executed",
    "failed",
]
SnapshotStatus = Literal["awaiting_approval", "resumed", "completed", "abandoned"]

TERMINAL_APPROVAL_STATUSES = {
    "approved",
    "rejected",
    "cancelled",
    "expired",
    "executed",
    "failed",
}
LIVE_SNAPSHOT_STATUSES = {"awaiting_approval", "resumed"}
LIVE_PENDING_APPROVAL_STATUSES = {"pending", "approved", "rejected"}
SNAPSHOT_SCOPE_META_KEY = "scope"

logger = logging.getLogger(__name__)
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class AgentRunSnapshot(Base):
    __tablename__ = "ai_agent_run_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('awaiting_approval','resumed','completed','abandoned')",
            name="ck_ai_agent_run_snapshots_status",
        ),
        Index(
            "ix_ai_agent_run_snapshots_conversation_status_created",
            "conversation_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_ai_agent_run_snapshots_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_ai_agent_run_snapshots_live_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status = 'awaiting_approval'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="awaiting_approval",
        server_default=text("'awaiting_approval'"),
    )
    messages_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    blocked_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    scrubbed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class ConversationRunLock(Base):
    __tablename__ = "ai_conversation_run_locks"
    __table_args__ = (
        CheckConstraint(
            "lock_kind IN ('chat')",
            name="ck_ai_conversation_run_locks_kind",
        ),
        Index(
            "uq_ai_conversation_run_locks_conversation",
            "conversation_id",
            unique=True,
        ),
        Index(
            "ix_ai_conversation_run_locks_workspace_expires",
            "workspace_id",
            "expires_at",
        ),
        Index(
            "ix_ai_conversation_run_locks_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(String(80), nullable=False)
    lock_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="chat",
        server_default=text("'chat'"),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AiToolApproval(Base):
    __tablename__ = "ai_tool_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled','expired','executed','failed')",
            name="ck_ai_tool_approvals_status",
        ),
        Index("ix_ai_tool_approvals_workspace_status", "workspace_id", "status"),
        Index("ix_ai_tool_approvals_conversation_status", "conversation_id", "status"),
        Index("ix_ai_tool_approvals_agent_run_id", "agent_run_id"),
        Index(
            "uq_ai_tool_approvals_agent_run_tool_call",
            "agent_run_id",
            "tool_call_id",
            unique=True,
        ),
        Index(
            "uq_ai_tool_approvals_pending_agent_run",
            "agent_run_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_run_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    tool_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False)
    resource_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    resolved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    execution_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


@dataclass(frozen=True)
class ReplayInvocationConfig:
    model: str | None
    policy: str | None
    chosen_pool: str | None
    parallel_tool_calls: bool | None
    tool_choice_state: str | dict[str, Any] | None
    stream_reasoning: bool | None
    temperature: float | None
    max_output_tokens: int | None
    raw: dict[str, Any]


def _default_expires_at() -> datetime:
    return utcnow_naive() + timedelta(hours=24)


def _normalize_resolution_reason(reason: str | None) -> str | None:
    if reason is None:
        return None
    normalized = reason.strip()
    return normalized or None


def _require_user_scope(
    workspace: Workspace, user: User, row_workspace_id: str, row_user_id: str
) -> None:
    if row_workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.approval_not_found",
        )
    if row_user_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ai.approval_different_user",
        )


def _serialize_execution_result(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def approval_to_payload(
    approval: AiToolApproval,
    *,
    snapshot: AgentRunSnapshot | None = None,
) -> dict[str, Any]:
    return {
        "id": approval.id,
        "workspace_id": approval.workspace_id,
        "conversation_id": approval.conversation_id,
        "agent_run_id": approval.agent_run_id,
        "tool_call_id": approval.tool_call_id,
        "tool_name": approval.tool_name,
        "arguments_json": approval.arguments_json,
        "resource_preview": approval.resource_preview,
        "status": approval.status,
        "requested_by_user_id": approval.requested_by_user_id,
        "resolved_by_user_id": approval.resolved_by_user_id,
        "reject_reason": approval.reject_reason,
        "resolved_at": approval.resolved_at,
        "expires_at": approval.expires_at,
        "execution_result_json": _serialize_execution_result(approval.execution_result_json),
        "error_message": approval.error_message,
        "created_at": approval.created_at,
        "snapshot_status": snapshot.status if snapshot is not None else None,
    }


def _load_approval_row(
    db: Session,
    *,
    approval_id: str,
    for_update: bool = False,
) -> AiToolApproval:
    stmt = select(AiToolApproval).where(AiToolApproval.id == approval_id)
    if for_update:
        stmt = stmt.with_for_update()
    approval = db.scalar(stmt)
    if approval is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.approval_not_found",
        )
    return approval


def get_approval(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    approval_id: str,
    for_update: bool = False,
) -> AiToolApproval:
    approval = _load_approval_row(db, approval_id=approval_id, for_update=for_update)
    _require_user_scope(workspace, user, approval.workspace_id, approval.requested_by_user_id)
    return approval


def get_live_pending_approval(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
) -> dict[str, Any] | None:
    snapshot = db.scalar(
        select(AgentRunSnapshot)
        .where(
            AgentRunSnapshot.conversation_id == conversation_id,
            AgentRunSnapshot.workspace_id == workspace.id,
            AgentRunSnapshot.requested_by_user_id == user.id,
            AgentRunSnapshot.status == "awaiting_approval",
        )
        .order_by(AgentRunSnapshot.created_at.desc())
    )
    if snapshot is None:
        return None
    approval = db.scalar(
        select(AiToolApproval)
        .where(
            AiToolApproval.agent_run_id == snapshot.id,
            AiToolApproval.status.in_(LIVE_PENDING_APPROVAL_STATUSES),
        )
        .order_by(AiToolApproval.created_at.desc())
    )
    if approval is None:
        return None
    if approval.status == "pending" and approval.expires_at <= utcnow_naive():
        # Re-fetch under row lock and re-check status so concurrent readers
        # do not each attempt to expire the same approval / abandon the same
        # snapshot.
        locked_approval = db.scalar(
            select(AiToolApproval).where(AiToolApproval.id == approval.id).with_for_update()
        )
        if locked_approval is not None and locked_approval.status == "pending":
            locked_snapshot = db.scalar(
                select(AgentRunSnapshot).where(AgentRunSnapshot.id == snapshot.id).with_for_update()
            )
            _expire_pending_approval(db, locked_approval, snapshot=locked_snapshot)
            if locked_approval.resolved_at is not None:
                elapsed_since_request_ms = max(
                    0,
                    int(
                        (locked_approval.resolved_at - locked_approval.created_at).total_seconds()
                        * 1000
                    ),
                )
                log_llm_tool_approval_resolved(
                    actor_user_id=user.id,
                    workspace_id=workspace.id,
                    approval_id=locked_approval.id,
                    tool_name=locked_approval.tool_name,
                    decision=locked_approval.status,
                    resolver_user_id=None,
                    elapsed_since_request_ms=elapsed_since_request_ms,
                )
        db.commit()
        return None
    return {
        "approval_id": approval.id,
        "agent_run_id": approval.agent_run_id,
        "call_id": approval.tool_call_id,
        "tool": approval.tool_name,
        "resource_preview": approval.resource_preview,
        "expires_at_ms": int(approval.expires_at.timestamp() * 1000),
        "status": approval.status,
        "reason": approval.reject_reason,
    }


def has_live_conversation_run(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
    for_update: bool = False,
) -> bool:
    # Lazily expire stale approvals before using snapshots as rewrite locks;
    # otherwise an expired pending approval can leave its awaiting snapshot
    # looking live until some other read path happens to touch it.
    get_live_pending_approval(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
    )
    expire_stale_conversation_run_locks(db)
    snapshot_stmt = (
        select(AgentRunSnapshot.id)
        .where(
            AgentRunSnapshot.conversation_id == conversation_id,
            AgentRunSnapshot.workspace_id == workspace.id,
            AgentRunSnapshot.requested_by_user_id == user.id,
            AgentRunSnapshot.status.in_(LIVE_SNAPSHOT_STATUSES),
        )
        .limit(1)
    )
    if for_update:
        snapshot_stmt = snapshot_stmt.with_for_update()
    if db.scalar(snapshot_stmt) is not None:
        return True

    lock_stmt = (
        select(ConversationRunLock.id)
        .where(
            ConversationRunLock.conversation_id == conversation_id,
            ConversationRunLock.workspace_id == workspace.id,
            ConversationRunLock.requested_by_user_id == user.id,
        )
        .limit(1)
    )
    if for_update:
        lock_stmt = lock_stmt.with_for_update()
    return db.scalar(lock_stmt) is not None


def _conversation_run_lock_expires_at() -> datetime:
    ttl_seconds = get_settings().ai_conversation_run_lock_ttl_seconds
    return utcnow_naive() + timedelta(seconds=ttl_seconds)


def expire_stale_conversation_run_locks(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    result = db.execute(
        delete(ConversationRunLock).where(ConversationRunLock.expires_at <= (now or utcnow_naive()))
    )
    return int(result.rowcount or 0)


def acquire_conversation_run_lock(
    db: Session,
    *,
    workspace: Workspace,
    conversation: Conversation,
    requested_by_user: User,
    lock_kind: Literal["chat"] = "chat",
) -> ConversationRunLock:
    get_live_pending_approval(
        db,
        workspace=workspace,
        user=requested_by_user,
        conversation_id=conversation.id,
    )
    expire_stale_conversation_run_locks(db)
    live_snapshot_id = db.scalar(
        select(AgentRunSnapshot.id)
        .where(
            AgentRunSnapshot.conversation_id == conversation.id,
            AgentRunSnapshot.workspace_id == workspace.id,
            AgentRunSnapshot.requested_by_user_id == requested_by_user.id,
            AgentRunSnapshot.status.in_(LIVE_SNAPSHOT_STATUSES),
        )
        .limit(1)
        .with_for_update()
    )
    if live_snapshot_id is not None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.conversation_run_active",
        )

    lock = ConversationRunLock(
        id=new_id(),
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        requested_by_user_id=requested_by_user.id,
        owner_id=new_id(),
        lock_kind=lock_kind,
        expires_at=_conversation_run_lock_expires_at(),
    )
    db.add(lock)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.conversation_run_active",
        ) from exc
    db.refresh(lock)
    return lock


def release_conversation_run_lock(
    db: Session,
    lock: ConversationRunLock,
) -> None:
    db.execute(
        delete(ConversationRunLock).where(
            ConversationRunLock.id == lock.id,
            ConversationRunLock.owner_id == lock.owner_id,
        )
    )
    db.commit()


def create_pending_approval(
    db: Session,
    *,
    workspace: Workspace,
    conversation: Conversation,
    requested_by_user: User,
    agent_run_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments_json: str,
    resource_preview: str | None,
    expires_at: datetime | None = None,
) -> AiToolApproval:
    approval = AiToolApproval(
        id=new_id(),
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        agent_run_id=agent_run_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments_json=arguments_json,
        resource_preview=resource_preview,
        status="pending",
        requested_by_user_id=requested_by_user.id,
        expires_at=expires_at or _default_expires_at(),
    )
    db.add(approval)
    db.flush()
    return approval


def record_approval_execution_result(
    db: Session,
    *,
    approval: AiToolApproval,
    execution_result: Any,
    status: Literal["rejected", "executed", "failed"] | None = None,
    error_message: str | None = None,
) -> None:
    approval.execution_result_json = json.dumps(execution_result, ensure_ascii=False)
    approval.error_message = error_message
    if status == "executed":
        approval.status = "executed"
    elif status == "failed":
        approval.status = "failed"
    db.add(approval)


def load_snapshot(
    db: Session,
    *,
    agent_run_id: str,
    for_update: bool = False,
) -> AgentRunSnapshot:
    stmt = select(AgentRunSnapshot).where(AgentRunSnapshot.id == agent_run_id)
    if for_update:
        stmt = stmt.with_for_update()
    snapshot = db.scalar(stmt)
    if snapshot is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.agent_run_snapshot_not_found",
        )
    return snapshot


def persist_snapshot_on_halt(
    db: Session,
    *,
    workspace: Workspace,
    conversation: Conversation,
    requested_by_user: User,
    messages_json: list[dict[str, Any]],
    blocked_call_id: str,
    model_meta: dict[str, Any] | None,
    snapshot_id: str | None = None,
) -> AgentRunSnapshot:
    snapshot = AgentRunSnapshot(
        id=snapshot_id or new_id(),
        conversation_id=conversation.id,
        workspace_id=workspace.id,
        requested_by_user_id=requested_by_user.id,
        status="awaiting_approval",
        messages_json=messages_json,
        blocked_call_id=blocked_call_id,
        model_meta=model_meta,
    )
    db.add(snapshot)
    db.flush()
    runtime_shadow.safe_runtime_shadow_write(
        db,
        snapshot=snapshot,
        operation=runtime_shadow.persist_runtime_shadow_on_halt,
    )
    return snapshot


def mark_snapshot_completed(db: Session, snapshot: AgentRunSnapshot) -> None:
    snapshot.status = "completed"
    db.add(snapshot)
    runtime_shadow.safe_runtime_shadow_write(
        db,
        snapshot=snapshot,
        operation=runtime_shadow.mark_runtime_shadow_completed,
    )


def mark_snapshot_resumed(db: Session, snapshot: AgentRunSnapshot) -> None:
    if snapshot.status != "awaiting_approval":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.agent_run_snapshot_not_awaiting_approval",
        )
    snapshot.status = "resumed"
    db.add(snapshot)
    runtime_shadow.safe_runtime_shadow_write(
        db,
        snapshot=snapshot,
        operation=runtime_shadow.mark_runtime_shadow_resumed,
    )


def rewind_snapshot_to_awaiting_approval(db: Session, snapshot: AgentRunSnapshot) -> None:
    snapshot.status = "awaiting_approval"
    db.add(snapshot)
    runtime_shadow.safe_runtime_shadow_write(
        db,
        snapshot=snapshot,
        operation=runtime_shadow.mark_runtime_shadow_awaiting_approval,
    )


def abandon_stale_snapshot(
    db: Session,
    snapshot: AgentRunSnapshot,
    *,
    cause: str,
) -> None:
    snapshot.status = "abandoned"
    db.add(snapshot)
    runtime_shadow.safe_runtime_shadow_write(
        db,
        snapshot=snapshot,
        operation=lambda session, *, snapshot: runtime_shadow.mark_runtime_shadow_abandoned(
            session,
            snapshot=snapshot,
            cause=cause,
        ),
    )


def _expire_pending_approval(
    db: Session,
    approval: AiToolApproval,
    *,
    snapshot: AgentRunSnapshot | None = None,
) -> None:
    approval.status = "expired"
    approval.resolved_at = utcnow_naive()
    db.add(approval)
    if snapshot is not None and snapshot.status == "awaiting_approval":
        abandon_stale_snapshot(db, snapshot, cause="approval_expired")


def _commit_expired_approval_and_raise(
    db: Session,
    *,
    approval: AiToolApproval,
    snapshot: AgentRunSnapshot | None = None,
) -> None:
    _expire_pending_approval(db, approval, snapshot=snapshot)
    db.commit()
    raise localized_http_exception(
        status_code=status.HTTP_410_GONE,
        code="ai.approval_expired",
    )


def resolve_approval(
    db: Session,
    *,
    workspace: Workspace,
    approval_id: str,
    decision: Literal["approved", "rejected"],
    reason: str | None,
    resolver_user: User,
) -> AiToolApproval:
    approval = get_approval(
        db,
        workspace=workspace,
        user=resolver_user,
        approval_id=approval_id,
        for_update=True,
    )
    snapshot = load_snapshot(db, agent_run_id=approval.agent_run_id, for_update=True)
    if approval.status != "pending":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.approval_already_status",
            status=approval.status,
        )
    if approval.expires_at <= utcnow_naive():
        _commit_expired_approval_and_raise(db, approval=approval, snapshot=snapshot)
    approval.status = decision
    approval.resolved_by_user_id = resolver_user.id
    approval.reject_reason = (
        _normalize_resolution_reason(reason) if decision == "rejected" else None
    )
    approval.resolved_at = utcnow_naive()
    db.add(approval)
    return approval


def abandon_approval(
    db: Session,
    *,
    workspace: Workspace,
    approval_id: str,
    reason: str | None,
    resolver_user: User,
) -> AiToolApproval:
    approval = get_approval(
        db,
        workspace=workspace,
        user=resolver_user,
        approval_id=approval_id,
        for_update=True,
    )
    snapshot = load_snapshot(db, agent_run_id=approval.agent_run_id, for_update=True)
    if approval.status != "pending":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.approval_already_status",
            status=approval.status,
        )
    if approval.expires_at <= utcnow_naive():
        _commit_expired_approval_and_raise(db, approval=approval, snapshot=snapshot)
    approval.status = "cancelled"
    approval.resolved_by_user_id = resolver_user.id
    approval.reject_reason = _normalize_resolution_reason(reason)
    approval.resolved_at = utcnow_naive()
    db.add(approval)
    abandon_stale_snapshot(db, snapshot, cause="approval_cancelled")
    return approval


def expire_stale_approvals(db: Session, older_than: datetime) -> int:
    approvals = list(
        db.scalars(
            select(AiToolApproval).where(
                AiToolApproval.status == "pending",
                AiToolApproval.expires_at < older_than,
            )
        )
    )
    count = 0
    for approval in approvals:
        snapshot = db.scalar(
            select(AgentRunSnapshot).where(AgentRunSnapshot.id == approval.agent_run_id)
        )
        _expire_pending_approval(db, approval, snapshot=snapshot)
        if approval.resolved_at is not None:
            elapsed_since_request_ms = max(
                0,
                int((approval.resolved_at - approval.created_at).total_seconds() * 1000),
            )
            log_llm_tool_approval_resolved(
                actor_user_id=None,
                workspace_id=approval.workspace_id,
                approval_id=approval.id,
                tool_name=approval.tool_name,
                decision=approval.status,
                resolver_user_id=None,
                elapsed_since_request_ms=elapsed_since_request_ms,
            )
        count += 1
    return count


def scrub_completed_snapshots(db: Session, *, older_than_days: int = 30) -> int:
    threshold = utcnow_naive() - timedelta(days=older_than_days)
    snapshots = list(
        db.scalars(
            select(AgentRunSnapshot).where(
                AgentRunSnapshot.status.in_(("completed", "abandoned")),
                AgentRunSnapshot.updated_at < threshold,
                AgentRunSnapshot.scrubbed_at.is_(None),
            )
        )
    )
    for snapshot in snapshots:
        snapshot.messages_json = None
        snapshot.model_meta = None
        snapshot.scrubbed_at = utcnow_naive()
        db.add(snapshot)
    return len(snapshots)


def rehydrate_model_meta(snapshot: AgentRunSnapshot) -> ReplayInvocationConfig:
    raw = dict(snapshot.model_meta or {})
    return ReplayInvocationConfig(
        model=raw.get("model"),
        policy=raw.get("policy"),
        chosen_pool=raw.get("chosen_pool"),
        parallel_tool_calls=raw.get("parallel_tool_calls"),
        tool_choice_state=raw.get("tool_choice_state"),
        stream_reasoning=raw.get("stream_reasoning"),
        temperature=raw.get("temperature"),
        max_output_tokens=raw.get("max_output_tokens"),
        raw=raw,
    )


def resolve_resume_allowed_app_ids(
    snapshot: AgentRunSnapshot,
    requested_allowed_app_ids: list[str] | None,
) -> list[str] | None:
    scope_meta = _snapshot_scope_meta(snapshot)
    stored_allowed_app_ids = scope_meta.get("allowed_app_ids")
    if stored_allowed_app_ids is None:
        return requested_allowed_app_ids

    stored_scope = _normalize_scope_list(stored_allowed_app_ids)
    if requested_allowed_app_ids is None:
        return stored_scope

    requested_scope = _normalize_scope_list(requested_allowed_app_ids)
    if not set(requested_scope).issubset(set(stored_scope)):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.resume_scope_wider",
        )
    return requested_scope


def ensure_resume_approved_tool_scope(
    approval: AiToolApproval,
    *,
    allowed_app_ids: list[str] | None,
    approved_tool_app_id: str | None,
) -> None:
    if approval.status != "approved" or allowed_app_ids is None or approved_tool_app_id is None:
        return
    if approved_tool_app_id in set(allowed_app_ids):
        return
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="ai.resume_scope_excludes_approved_tool",
    )


def filter_resume_tool_specs(
    snapshot: AgentRunSnapshot,
    tool_specs: list[AgentToolSpec],
) -> list[AgentToolSpec]:
    frozen_tool_names = _frozen_resume_tool_names(snapshot)
    if not frozen_tool_names:
        return tool_specs
    return [spec for spec in tool_specs if spec.name in frozen_tool_names]


def get_resume_context(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
    approval_id: str,
    for_update: bool = False,
) -> tuple[AiToolApproval, AgentRunSnapshot]:
    approval = get_approval(
        db,
        workspace=workspace,
        user=user,
        approval_id=approval_id,
        for_update=for_update,
    )
    if approval.conversation_id != conversation_id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.approval_conversation_mismatch",
        )
    snapshot = load_snapshot(
        db,
        agent_run_id=approval.agent_run_id,
        for_update=for_update,
    )
    if snapshot.workspace_id != workspace.id or snapshot.requested_by_user_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.agent_run_snapshot_not_found",
        )
    if approval.status == "pending":
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.approval_resume_requires_resolution",
        )
    if approval.status in {"cancelled", "expired"}:
        raise localized_http_exception(
            status_code=status.HTTP_410_GONE,
            code="ai.approval_resume_unavailable",
        )
    if snapshot.status == "resumed":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.agent_run_already_resuming",
        )
    if snapshot.status in {"completed", "abandoned"}:
        raise localized_http_exception(
            status_code=status.HTTP_410_GONE,
            code="ai.agent_run_snapshot_not_resumable",
        )
    return approval, snapshot


def _snapshot_scope_meta(snapshot: AgentRunSnapshot) -> dict[str, Any]:
    raw = dict(snapshot.model_meta or {})
    scope_meta = raw.get(SNAPSHOT_SCOPE_META_KEY)
    if isinstance(scope_meta, dict):
        return scope_meta
    return {}


def _normalize_scope_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _tool_names_from_specs(tool_specs: list[AgentToolSpec]) -> set[str]:
    return set(agent_tool_names(tool_specs))


def _frozen_resume_tool_names(snapshot: AgentRunSnapshot) -> set[str]:
    return set(_normalize_scope_list(_snapshot_scope_meta(snapshot).get("resolved_tool_names")))
