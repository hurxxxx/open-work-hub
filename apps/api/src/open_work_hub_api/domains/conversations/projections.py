from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.conversations.default_scope_adapters import is_supported_conversation_scope_ref
from open_work_hub_api.domains.conversations.schemas import (
    ArtifactOut,
    ConversationDetail,
    ConversationLivePendingApproval,
    ConversationSummary,
    ConversationTurnOut,
)


def conversation_summary_from_row(row: Any) -> ConversationSummary:
    scope_ref, scope_resource_id = _supported_scope(row)
    return ConversationSummary(
        id=row.id,
        title=row.title,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def conversation_turn_out_from_row(turn: Any) -> ConversationTurnOut:
    meta = turn.meta or {}
    return ConversationTurnOut(
        id=turn.id,
        seq=turn.seq,
        role=turn.role,
        content=turn.content,
        reasoning=meta.get("reasoning"),
        reasoning_status=meta.get("reasoning_status"),
        finish_reason=meta.get("finish_reason"),
        response_status=meta.get("response_status"),
        provider=meta.get("provider"),
        policy=meta.get("policy"),
        chosen_pool=meta.get("chosen_pool"),
        decision_reason=meta.get("decision_reason"),
        forced_local=meta.get("forced_local"),
        pii_hits=list(meta.get("pii_hits") or []),
        tool_calls=list(meta.get("tool_calls") or []),
        pending_approvals=list(meta.get("pending_approvals") or []),
        artifacts=_artifacts_from_meta(meta),
        created_at=turn.created_at,
    )


def conversation_detail_from_row(
    row: Any,
    *,
    live_pending_approval: dict[str, Any] | None = None,
) -> ConversationDetail:
    scope_ref, scope_resource_id = _supported_scope(row)
    return ConversationDetail(
        id=row.id,
        title=row.title,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        live_pending_approval=(
            ConversationLivePendingApproval.model_validate(live_pending_approval)
            if live_pending_approval is not None
            else None
        ),
        turns=[conversation_turn_out_from_row(turn) for turn in row.turns],
    )


def _supported_scope(row: Any) -> tuple[str | None, str | None]:
    scope_ref = row.scope_ref if row.scope_ref and is_supported_conversation_scope_ref(row.scope_ref) else None
    scope_resource_id = row.scope_resource_id if scope_ref is not None else None
    return scope_ref, scope_resource_id


def _artifacts_from_meta(meta: dict[str, Any]) -> list[ArtifactOut]:
    raw_artifacts = meta.get("artifacts") or []
    artifacts: list[ArtifactOut] = []
    for record in raw_artifacts:
        if not isinstance(record, dict):
            continue
        artifact_id = record.get("id")
        if not artifact_id:
            continue
        artifacts.append(
            ArtifactOut(
                id=artifact_id,
                type=record.get("type") or "document",
                title=record.get("title"),
                language=record.get("language"),
                content=record.get("content") or "",
                status=record.get("status"),
            )
        )
    return artifacts
