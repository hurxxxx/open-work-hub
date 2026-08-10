from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.ai_artifacts.contracts import (
    AiArtifactCreate,
    AiArtifactQueryCreate,
    AiArtifactSourceCreate,
)
from open_alm_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_alm_api.domains.ai_artifacts.models import AiArtifact
from open_alm_api.domains.ai_graph.runtime import AiGraphRuntimeContext
from open_alm_api.domains.conversations import service as conversations_service
from open_alm_api.domains.legacy_issues.analysis_graph.contracts import (
    AnalysisDataBundle,
    require_complete_analysis_data,
)


class AiArtifactAnalysisWriter:
    """Atomically finalize an artifact and its conversation placeholder."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    def persist(
        self,
        *,
        context: AiGraphRuntimeContext,
        artifact_type: str,
        title: str,
        markdown: str,
        data: AnalysisDataBundle,
        input_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        require_complete_analysis_data(data)
        assistant_turn_id = _required_text(input_payload, "assistant_turn_id")
        with self._session_factory() as db:
            try:
                repository = AiArtifactRepository(db)
                completed = _completed_artifact(db, context.run_id)
                if completed is not None:
                    return _completed_artifact_result(
                        completed,
                        context=context,
                        artifact_type=artifact_type,
                        assistant_turn_id=assistant_turn_id,
                    )
                pending = db.scalar(
                    select(AiArtifact)
                    .where(
                        AiArtifact.graph_run_id == context.run_id,
                        AiArtifact.status == "pending",
                    )
                    .order_by(AiArtifact.created_at, AiArtifact.id)
                    .limit(1)
                    .with_for_update()
                )
                if pending is None:
                    completed = _completed_artifact(db, context.run_id)
                    if completed is not None:
                        return _completed_artifact_result(
                            completed,
                            context=context,
                            artifact_type=artifact_type,
                            assistant_turn_id=assistant_turn_id,
                        )
                    raise LookupError(
                        f"pending graph artifact not found: {context.run_id}"
                    )
                artifact_payload = _artifact_payload(input_payload, data=data)
                if (
                    pending.graph_run_id == context.run_id
                    and pending.artifact_type == artifact_type
                ):
                    artifact = repository.start_building(pending)
                    repository.update_building(
                        artifact,
                        content_text=markdown,
                        payload=artifact_payload,
                        title=title,
                    )
                else:
                    repository.fail(
                        pending,
                        error_code="ai.artifact_type_replaced",
                    )
                    artifact = repository.create_building(
                        AiArtifactCreate(
                            workspace_id=context.workspace_id,
                            owner_user_id=context.requested_by_user_id,
                            app_id=context.app_id,
                            artifact_type=artifact_type,
                            title=title,
                            content_text=markdown,
                            payload=artifact_payload,
                            graph_run_id=context.run_id,
                            conversation_id=context.conversation_id,
                            conversation_turn_id=assistant_turn_id,
                            visibility="private",
                        )
                    )
                for query in _query_records(data):
                    repository.add_query(artifact, query)
                for source in _source_records(data):
                    repository.add_source(artifact, source)
                repository.complete(artifact)
                conversations_service.update_staged_or_persisted_turn(
                    db,
                    turn_id=assistant_turn_id,
                    content=(
                        "요청하신 보고서를 생성했습니다."
                        if artifact_type == "report"
                        else markdown
                    ),
                    meta={
                        "finish_reason": "stop",
                        "response_status": "completed",
                        "provider": "server",
                        "policy": "durable_ai_graph",
                        "agent_run_id": context.run_id,
                        "artifacts": [
                            {
                                "id": artifact.id,
                                "type": "document",
                                "title": title,
                                "language": "markdown",
                                "content": (
                                    ""
                                    if artifact_type == "report"
                                    else markdown
                                ),
                                "status": "closed",
                            }
                        ],
                    },
                )
                db.commit()
                return {
                    "artifact_id": artifact.id,
                    "artifact_number": artifact.artifact_number,
                    "artifact_type": artifact.artifact_type,
                }
            except Exception:
                db.rollback()
                raise


def _completed_artifact(db: Session, run_id: str) -> AiArtifact | None:
    return db.scalar(
        select(AiArtifact)
        .where(
            AiArtifact.graph_run_id == run_id,
            AiArtifact.status == "completed",
        )
        .order_by(AiArtifact.completed_at.desc(), AiArtifact.id.desc())
        .limit(1)
    )


def _completed_artifact_result(
    artifact: AiArtifact,
    *,
    context: AiGraphRuntimeContext,
    artifact_type: str,
    assistant_turn_id: str,
) -> dict[str, Any]:
    expected = {
        "workspace_id": context.workspace_id,
        "owner_user_id": context.requested_by_user_id,
        "app_id": context.app_id,
        "conversation_id": context.conversation_id,
        "conversation_turn_id": assistant_turn_id,
        "artifact_type": artifact_type,
    }
    mismatches = [
        name
        for name, value in expected.items()
        if getattr(artifact, name) != value
    ]
    if mismatches:
        raise ValueError(
            "completed graph artifact does not match execution context: "
            + ", ".join(mismatches)
        )
    return {
        "artifact_id": artifact.id,
        "artifact_number": artifact.artifact_number,
        "artifact_type": artifact.artifact_type,
    }


def _artifact_payload(
    input_payload: Mapping[str, Any],
    *,
    data: AnalysisDataBundle,
) -> dict[str, Any]:
    """Keep the originating request beside the durable report.

    Graph bootstrap inputs are deliberately removed after terminal execution.
    The private artifact therefore owns the immutable request snapshot used by
    later quality analysis, without relying on conversation-turn adjacency.
    """

    return {
        "schema_version": 2,
        "request": {
            "kind": "user_question",
            "text": _required_text(input_payload, "question"),
        },
        "analysis_health": {
            "status": (
                "degraded"
                if (
                    data.limitations
                    or data.capability_limitations
                    or data.execution_warnings
                )
                else "complete"
            ),
            "limitations": list(dict.fromkeys(data.limitations)),
            "capability_limitations": list(
                dict.fromkeys(data.capability_limitations)
            ),
            "execution_warnings": list(
                dict.fromkeys(data.execution_warnings)
            ),
            "source_revisions": _source_revisions(data),
        },
    }


def _source_revisions(data: AnalysisDataBundle) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for revision in data.source_revisions:
        revision_id = str(revision.revision_id or "").strip()
        if not revision_id or revision_id in seen:
            continue
        seen.add(revision_id)
        revisions.append(
            {
                "revision_id": revision_id,
                "status": revision.status,
                "module_key": revision.module_key,
            }
        )
    for evidence in data.evidence:
        revision_id = str(evidence.revision_id or "").strip()
        if not revision_id or revision_id in seen:
            continue
        seen.add(revision_id)
        revisions.append(
            {
                "revision_id": revision_id,
                "status": evidence.metadata.get("revision_status"),
                "module_key": evidence.metadata.get("module_key"),
            }
        )
    return revisions


def mark_analysis_placeholder_failed(
    *,
    run_id: str,
    assistant_turn_id: str,
    error_code: str,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    resolved_factory = session_factory or get_session_factory()
    with resolved_factory() as db:
        try:
            conversations_service.update_staged_or_persisted_turn(
                db,
                turn_id=assistant_turn_id,
                content=(
                    "분석을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요."
                ),
                meta={
                    "finish_reason": "error",
                    "response_status": "error",
                    "provider": "server",
                    "policy": "durable_ai_graph",
                    "agent_run_id": run_id,
                    "error_code": error_code,
                    "artifacts": [],
                },
            )
            db.commit()
        except Exception:
            db.rollback()
            raise


def _query_records(data: AnalysisDataBundle) -> list[AiArtifactQueryCreate]:
    records: list[AiArtifactQueryCreate] = []
    for item in data.query_results:
        rows = [dict(row) for row in item.rows]
        records.append(
            AiArtifactQueryCreate(
                query_kind="sql",
                title=item.recipe_id or "동적 정형 조회",
                family_id=item.recipe_id,
                query_spec={
                    "query_id": item.query_id,
                    "source": "recipe" if item.recipe_id else "safe_sql",
                    "recipe_arguments": item.recipe_arguments,
                },
                statement_text=item.sql,
                typed_params=item.params,
                execution_status=(
                    "completed"
                    if item.status == "succeeded"
                    else "failed"
                    if item.status == "failed"
                    else "not_executed"
                ),
                error_code=item.error_code,
                result_schema=[
                    {"name": column, "type": _column_type(rows, column)}
                    for column in item.columns
                ],
                result_rows=rows,
                result_sha256=_rows_sha256(rows) if item.status == "succeeded" else None,
                row_count=item.row_count,
                duration_ms=item.duration_ms,
                truncated=item.truncated,
                payload_bytes=len(
                    str(rows).encode("utf-8")
                ),
                exactness="exact",
            )
        )
    return records


def _source_records(data: AnalysisDataBundle) -> list[AiArtifactSourceCreate]:
    records: list[AiArtifactSourceCreate] = []
    for item in data.evidence:
        row = {
            "evidence_id": item.evidence_id,
            "title": item.title,
            "excerpt": item.excerpt,
            "record_id": item.record_id,
            "revision_id": item.revision_id,
        }
        records.append(
            AiArtifactSourceCreate(
                source_kind=item.source_kind,
                source_ref=item.record_id or item.evidence_id,
                source_version=item.revision_id,
                title=item.title,
                locator={
                    "record_id": item.record_id,
                    "revision_id": item.revision_id,
                },
                metadata=item.metadata,
                content_sha256=hashlib.sha256(
                    item.excerpt.encode("utf-8")
                ).hexdigest(),
                grid_columns=[
                    {"key": key, "label": key}
                    for key in row
                ],
                grid_rows=[row],
                row_count=1,
                truncated=False,
            )
        )
    return records


def _rows_sha256(rows: list[dict[str, Any]]) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _column_type(rows: list[dict[str, Any]], column: str) -> str:
    value = next(
        (row.get(column) for row in rows if row.get(column) is not None),
        None,
    )
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "text"


def _required_text(values: Mapping[str, Any], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"analysis graph input is missing: {key}")
    return value.strip()


__all__ = [
    "AiArtifactAnalysisWriter",
    "mark_analysis_placeholder_failed",
]
