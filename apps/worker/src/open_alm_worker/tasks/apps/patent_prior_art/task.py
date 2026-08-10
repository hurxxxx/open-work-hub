"""Durable worker task for private patent prior-art jobs."""

from __future__ import annotations

import logging
from threading import Event, Thread

from celery.exceptions import Ignore

from open_alm_worker.celery_app import celery_app
from open_alm_worker.queue_contract import (
    PATENT_PRIOR_ART_RECOVER_TASK_NAME,
    PATENT_PRIOR_ART_REPUBLISH_TASK_NAME,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
)
from open_alm_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
)


_ensure_api_src_on_path()

from open_alm_api.domains.patent_prior_art import service as prior_art_service  # noqa: E402
from open_alm_api.domains.patent_prior_art.pipeline import (  # noqa: E402
    PatentPriorArtPipelineCancelled,
    PatentPriorArtTransientError,
    run_patent_prior_art,
)
from open_alm_api.domains.patent_prior_art.service import (  # noqa: E402
    PatentPriorArtPersistenceCancelled,
)


logger = logging.getLogger(__name__)
_HEARTBEAT_INTERVAL_SECONDS = 30.0

_PIPELINE_STAGE_MAP = {
    "validated": "searching",
    "searching": "searching",
    "ranking": "ranking",
    "assessment": "assessing",
    "reporting": "reporting",
    # The pipeline has produced its in-memory result, but the durable artifacts
    # and projections are not complete until persist_result commits them.
    "completed": "persisting",
}


class _PatentPriorArtAccessRevoked(RuntimeError):
    """Raised when the owner loses access while a fenced execution is active."""


class _ExecutionLeaseHeartbeat:
    def __init__(self, *, job_id: str, execution_id: str) -> None:
        self.job_id = job_id
        self.execution_id = execution_id
        self.stop_event = Event()
        self.lost_event = Event()
        self.thread = Thread(
            target=self._run,
            name=f"patent-prior-art-heartbeat-{job_id}",
            daemon=True,
        )

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self.stop_event.wait(_HEARTBEAT_INTERVAL_SECONDS):
            session = _db_session()
            try:
                if not prior_art_service.renew_execution_lease(
                    session,
                    job_id=self.job_id,
                    execution_id=self.execution_id,
                ):
                    self.lost_event.set()
                    return
            except Exception:
                logger.warning(
                    "patent prior-art execution heartbeat failed for job %s",
                    self.job_id,
                    exc_info=True,
                )
            finally:
                session.close()


@celery_app.task(
    name=PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
    bind=True,
    acks_late=True,
    max_retries=0,
    task_time_limit=1800,
    task_soft_time_limit=1740,
)
def run_patent_prior_art_job(self, job_id: str) -> str:
    """Run one job without exposing provider errors or retrying unsafe failures."""

    session = _db_session()
    row = None
    execution_id: str | None = None
    heartbeat: _ExecutionLeaseHeartbeat | None = None
    try:
        task_id = getattr(self.request, "id", None)
        row = prior_art_service.claim_job(
            session,
            job_id=job_id,
            task_id=task_id,
        )
        if row is None:
            raise Ignore()
        execution_id = row.execution_id
        if not execution_id:
            raise Ignore()
        heartbeat = _ExecutionLeaseHeartbeat(job_id=row.id, execution_id=execution_id)
        heartbeat.start()

        def require_execution_access() -> None:
            if heartbeat is not None and heartbeat.lost_event.is_set():
                raise PatentPriorArtPipelineCancelled()
            if prior_art_service.can_execute_job(
                session,
                row,
                execution_id=execution_id,
            ):
                return
            if prior_art_service.is_cancelled(
                session,
                job_id=job_id,
                execution_id=execution_id,
            ):
                raise PatentPriorArtPipelineCancelled()
            raise _PatentPriorArtAccessRevoked()

        require_execution_access()

        job_input = prior_art_service.load_job_input(row)

        def report_progress(percent: int, pipeline_stage: str) -> None:
            stage = _PIPELINE_STAGE_MAP.get(pipeline_stage)
            if stage is None:
                raise ValueError("unsupported patent prior-art pipeline stage")
            if not prior_art_service.update_stage(
                session,
                row,
                execution_id=execution_id,
                stage=stage,
                progress_percent=percent,
            ):
                raise PatentPriorArtPipelineCancelled()

        def was_cancelled() -> bool:
            require_execution_access()
            return False

        result = run_patent_prior_art(
            session,
            workspace_id=row.workspace_id,
            actor_user_id=row.owner_id,
            title=job_input.title,
            invention_text=job_input.invention_text,
            technology_summary=job_input.technology_summary,
            jurisdictions=job_input.jurisdictions,
            search_plan=job_input.search_plan,
            progress_callback=report_progress,
            cancel_callback=was_cancelled,
        )
        require_execution_access()
        prior_art_service.persist_result(
            session,
            row,
            execution_id=execution_id,
            result=result,
        )
        return row.id
    except Ignore:
        raise
    except _PatentPriorArtAccessRevoked:
        if row is not None and execution_id is not None:
            prior_art_service.mark_failed(
                session,
                row,
                execution_id=execution_id,
                failure_code="access_revoked",
            )
        raise Ignore()
    except (PatentPriorArtPipelineCancelled, PatentPriorArtPersistenceCancelled):
        raise Ignore()
    except PatentPriorArtTransientError as error:
        del error
        if row is not None and execution_id is not None:
            scheduled = prior_art_service.schedule_automatic_restart(
                session,
                row,
                execution_id=execution_id,
            )
            if not scheduled:
                prior_art_service.mark_failed(
                    session,
                    row,
                    execution_id=execution_id,
                    failure_code="provider_timeout",
                )
        logger.warning("patent prior-art provider timed out for job %s", job_id)
        raise Ignore()
    except Exception as error:
        logger.error(
            "patent prior-art job %s failed with %s",
            job_id,
            type(error).__name__,
        )
        if row is not None and execution_id is not None:
            prior_art_service.mark_failed(
                session,
                row,
                execution_id=execution_id,
                failure_code="pipeline_failed",
            )
        raise Ignore()
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        session.close()


@celery_app.task(
    name=PATENT_PRIOR_ART_REPUBLISH_TASK_NAME,
    task_time_limit=60,
    task_soft_time_limit=45,
)
def republish_pending_patent_prior_art_jobs(limit: int = 100) -> int:
    """Republish durable queued jobs whose broker acknowledgement is ambiguous."""

    session = _db_session()
    try:
        return prior_art_service.republish_pending_jobs(session, limit=limit)
    finally:
        session.close()


@celery_app.task(
    name=PATENT_PRIOR_ART_RECOVER_TASK_NAME,
    task_time_limit=60,
    task_soft_time_limit=45,
)
def recover_patent_prior_art_jobs(limit: int = 100) -> dict[str, int]:
    """Recover expired/due work from DB state, then publish fresh fences."""

    session = _db_session()
    try:
        return prior_art_service.recover_jobs(session, limit=limit)
    finally:
        session.close()


__all__ = [
    "republish_pending_patent_prior_art_jobs",
    "recover_patent_prior_art_jobs",
    "run_patent_prior_art_job",
]
