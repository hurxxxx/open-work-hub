from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.ai_artifacts.models import AiArtifact
from open_work_hub_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_work_hub_api.domains.ai_graph.models import AiGraphRun
from open_work_hub_api.domains.ai_graph.repository import AiGraphRunRepository
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)


def enforce_graph_run_app_policy(
    db: Session,
    *,
    run_id: str,
    claim_token: str | None,
    stage: str,
) -> bool:
    """Lock and recheck the owning app at an execution seam.

    The caller owns the transaction and decides when terminal input cleanup is
    safe. A disabled run is terminalized here so no caller can accidentally
    retry it through a different executor.
    """

    run = db.scalar(select(AiGraphRun).where(AiGraphRun.id == run_id).with_for_update())
    if run is None:
        raise LookupError(run_id)
    if run.status in {"completed", "failed", "cancelled"}:
        return run.status != "cancelled"
    if can_use_app(
        db,
        app_id=run.app_id,
        user_id=run.requested_by_user_id,
    ):
        return True
    AiGraphRunRepository(db).transition(
        run.id,
        "cancelled",
        stage=stage,
        status_message_key="ai.graphRun.cancelled",
        error_code="app_execution_disabled",
        claim_token=claim_token,
    )
    artifact_repository = AiArtifactRepository(db)
    artifacts = db.scalars(
        select(AiArtifact).where(
            AiArtifact.graph_run_id == run.id,
            AiArtifact.status.in_(("pending", "building")),
        )
    ).all()
    for artifact in artifacts:
        artifact_repository.fail(artifact, error_code="app_execution_disabled")
    return False


__all__ = ["enforce_graph_run_app_policy"]
