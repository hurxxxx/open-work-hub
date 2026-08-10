from __future__ import annotations

from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from ai_do_api.domains.ai_artifacts.contracts import AiArtifactCreate
from ai_do_api.domains.ai_graph.contracts import AiGraphRunRequest
from ai_do_api.domains.ai_graph.dispatch import stage_graph_dispatch
from ai_do_api.domains.ai_graph.publication import publish_pending_graph_dispatches
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.conversations import service as conversations_service
from ai_do_api.domains.conversations.models import Conversation
from ai_do_api.domains.legacy_issues.analysis_graph.topology import (
    legacy_issue_analysis_graph_spec,
)


_PLACEHOLDER_CONTENT = "요청을 접수했습니다. 분석을 진행하고 있습니다."


def dispatch_legacy_issue_analysis(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation: Conversation,
    question: str,
    recent_messages: Sequence[Mapping[str, str]],
) -> tuple[str, str, str]:
    """Atomically stage placeholder, graph input, artifact, and dispatch outbox."""

    assistant_turn = conversations_service.stage_turn(
        db,
        conversation=conversation,
        role="assistant",
        content=_PLACEHOLDER_CONTENT,
        meta={
            "finish_reason": None,
            "response_status": "streaming",
            "provider": "server",
            "policy": "durable_ai_graph",
            "artifacts": [],
        },
    )
    graph = legacy_issue_analysis_graph_spec()
    inputs = {
        "question": question,
        "recent_messages": [
            {
                "role": str(message.get("role") or ""),
                "content": str(message.get("content") or "")[:4_000],
            }
            for message in recent_messages[-8:]
            if str(message.get("role") or "") in {"user", "assistant"}
        ],
        "assistant_turn_id": assistant_turn.id,
    }
    prepared = stage_graph_dispatch(
        db,
        run_request=AiGraphRunRequest(
            workspace_id=workspace.id,
            requested_by_user_id=user.id,
            app_id="legacy-issues",
            graph=graph,
            inputs=inputs,
            conversation_id=conversation.id,
            visibility="private",
        ),
        pending_artifact=AiArtifactCreate(
            workspace_id=workspace.id,
            owner_user_id=user.id,
            app_id="legacy-issues",
            artifact_type="analysis",
            title="과거차 문제점 분석",
            payload={
                "schema_version": 1,
                "request": {
                    "kind": "user_question",
                    "text": question,
                },
            },
            graph_run_id=None,
            conversation_id=conversation.id,
            conversation_turn_id=assistant_turn.id,
            visibility="private",
        ),
    )
    assistant_turn.meta = {
        **(assistant_turn.meta or {}),
        "agent_run_id": prepared.graph_run.id,
        "artifact_id": prepared.pending_artifact.id,
    }
    db.add(assistant_turn)
    db.commit()
    publish_pending_graph_dispatches(db)
    return (
        prepared.graph_run.id,
        prepared.pending_artifact.id,
        assistant_turn.id,
    )

__all__ = [
    "dispatch_legacy_issue_analysis",
]
