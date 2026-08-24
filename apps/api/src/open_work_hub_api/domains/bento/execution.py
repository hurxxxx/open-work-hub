"""Durable Bento AI job executor registered with the shared AI graph worker."""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from uuid import uuid4

from sqlalchemy import select, update

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai.agent_runtime import (
    AgentRuntimeRequest,
    get_agent_runtime_adapter,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    resolve_ai_model_workload_route,
)
from open_work_hub_api.domains.ai_graph.execution_registry import register_ai_graph_executor
from open_work_hub_api.domains.ai_graph.repository import (
    AiGraphExecutionLeaseLostError,
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.bento import (
    BENTO_EDIT_WORKLOAD_ID,
    BENTO_GENERATE_WORKLOAD_ID,
)
from open_work_hub_api.domains.bento.agent_runtime import (
    AgentRuntimeCancelled,
    ensure_bento_agent_runtime_adapters_registered,
)
from open_work_hub_api.domains.bento.models import (
    BentoAiJob,
    BentoAiJobInput,
    BentoDocument,
)


BENTO_AGENT_GRAPH_ID = "bento.agent"
BENTO_AGENT_GRAPH_VERSION = "1"
logger = logging.getLogger(__name__)


def execute_bento_agent_job(run_id: str) -> str:
    claim_token = uuid4().hex
    session_factory = get_session_factory()
    with session_factory() as db:
        repository = AiGraphRunRepository(db)
        claim = repository.claim_execution(
            run_id,
            claim_token=claim_token,
            lease_duration=timedelta(minutes=25),
        )
        if not claim.acquired:
            return claim.reason or claim.status
        job = db.get(BentoAiJob, run_id)
        job_input = db.get(BentoAiJobInput, run_id)
        if job is None or job_input is None:
            repository.transition(
                run_id,
                "failed",
                error_code="bento.job_input_missing",
                claim_token=claim_token,
            )
            db.commit()
            return "failed"
        job.status = "running"
        job.started_at = job.started_at or utcnow_naive()
        job.updated_at = utcnow_naive()
        db.commit()

        workload_id = (
            BENTO_GENERATE_WORKLOAD_ID if job.kind == "create" else BENTO_EDIT_WORKLOAD_ID
        )

        def cancelled() -> bool:
            return (
                db.scalar(
                    select(BentoAiJob.cancel_requested_at).where(BentoAiJob.id == run_id)
                )
                is not None
            )

        def progress(stage: str, percent: int) -> None:
            repository.transition(
                run_id,
                "running",
                stage=stage,
                progress_percent=min(99, max(0, percent)),
                status_message_key=stage,
                claim_token=claim_token,
            )
            repository.renew_execution_lease(
                run_id,
                claim_token=claim_token,
                lease_duration=timedelta(minutes=25),
            )
            db.commit()

        try:
            route = resolve_ai_model_workload_route(db, workload_id=workload_id)
            if route.runtime_adapter_id != job.runtime_adapter_id:
                raise RuntimeError("bento.runtime_configuration_changed")
            adapter = get_agent_runtime_adapter(job.runtime_adapter_id)
            result = adapter.run(
                AgentRuntimeRequest(
                    run_id=run_id,
                    workspace_id=job.workspace_id,
                    actor_user_id=job.requested_by_id,
                    workload_id=workload_id,
                    route=route,
                    input_payload={
                        "db": db,
                        "kind": job.kind,
                        "prompt": job_input.prompt,
                        "current_document_json": job_input.current_document_json,
                        "slide_count": job.slide_count,
                        "language": job.language,
                    },
                    progress=progress,
                    cancelled=cancelled,
                )
            )
            if cancelled():
                raise AgentRuntimeCancelled()
            document_json = str(result.output_payload["document_json"])
            parsed = json.loads(document_json)
            title = str(parsed["title"]).strip()
            if job.kind == "create":
                document = BentoDocument(
                    id=str(uuid4()),
                    workspace_id=job.workspace_id,
                    owner_id=job.requested_by_id,
                    title=title,
                    visibility=job.visibility,
                    document_json=document_json,
                    version=1,
                )
                db.add(document)
                db.flush()
                result_document_id = document.id
                result_version = 1
            else:
                if job.target_document_id is None or job.base_version is None:
                    raise RuntimeError("bento.job_target_missing")
                update_result = db.execute(
                    update(BentoDocument)
                    .where(
                        BentoDocument.id == job.target_document_id,
                        BentoDocument.workspace_id == job.workspace_id,
                        BentoDocument.version == job.base_version,
                        BentoDocument.archived_at.is_(None),
                    )
                    .values(
                        title=title,
                        document_json=document_json,
                        version=job.base_version + 1,
                        updated_at=utcnow_naive(),
                    )
                )
                if update_result.rowcount != 1:
                    raise RuntimeError("bento.version_conflict")
                result_document_id = job.target_document_id
                result_version = job.base_version + 1

            now = utcnow_naive()
            job.status = "succeeded"
            job.result_document_id = result_document_id
            job.result_version = result_version
            job.finished_at = now
            job.updated_at = now
            repository.transition(
                run_id,
                "completed",
                stage="bento.ai.completed",
                status_message_key="bento.ai.completed",
                claim_token=claim_token,
            )
            db.delete(job_input)
            AiGraphRunInputRepository(db).delete_after_terminal(run_id)
            db.commit()
            return "completed"
        except AgentRuntimeCancelled:
            db.rollback()
            _finish_failed_or_cancelled(
                db,
                run_id=run_id,
                claim_token=claim_token,
                cancelled=True,
                error_code=None,
            )
            return "cancelled"
        except Exception as error:
            db.rollback()
            error_code = _error_code(error)
            logger.exception("Bento agent job failed: run_id=%s code=%s", run_id, error_code)
            _finish_failed_or_cancelled(
                db,
                run_id=run_id,
                claim_token=claim_token,
                cancelled=False,
                error_code=error_code,
            )
            return "failed"


def _finish_failed_or_cancelled(
    db,
    *,
    run_id: str,
    claim_token: str,
    cancelled: bool,
    error_code: str | None,
) -> None:
    job = db.get(BentoAiJob, run_id)
    if job is not None:
        job.status = "cancelled" if cancelled else "failed"
        job.error_code = error_code
        job.finished_at = utcnow_naive()
        job.updated_at = utcnow_naive()
    repository = AiGraphRunRepository(db)
    try:
        repository.transition(
            run_id,
            "cancelled" if cancelled else "failed",
            stage="bento.ai.cancelled" if cancelled else "bento.ai.failed",
            status_message_key=(
                "bento.ai.cancelled" if cancelled else "bento.ai.failed"
            ),
            error_code=error_code,
            claim_token=claim_token,
        )
    except AiGraphExecutionLeaseLostError:
        db.rollback()
        return
    job_input = db.get(BentoAiJobInput, run_id)
    if job_input is not None:
        db.delete(job_input)
    AiGraphRunInputRepository(db).delete_after_terminal(run_id)
    db.commit()


def _error_code(error: Exception) -> str:
    if isinstance(error, AiModelSettingsError):
        return error.code
    value = str(error).strip()
    if value.startswith(("bento.", "admin.")) and len(value) <= 160:
        return value
    return f"bento.agent.{type(error).__name__}"[:160]


def ensure_bento_agent_executor_registered() -> None:
    ensure_bento_agent_runtime_adapters_registered()
    register_ai_graph_executor(
        BENTO_AGENT_GRAPH_ID,
        BENTO_AGENT_GRAPH_VERSION,
        execute_bento_agent_job,
    )


__all__ = [
    "BENTO_AGENT_GRAPH_ID",
    "BENTO_AGENT_GRAPH_VERSION",
    "ensure_bento_agent_executor_registered",
    "execute_bento_agent_job",
]
