from __future__ import annotations

import asyncio

from celery.exceptions import SoftTimeLimitExceeded

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.queue_contract import (
    HERMES_REPUBLISH_TASK_NAME,
    HERMES_RUN_TASK_NAME,
)
from open_work_hub_worker.runtime import db_session
from open_work_hub_worker.settings import get_settings

from open_work_hub_api.domains.hermes.client import HermesClientError
from open_work_hub_api.domains.hermes.execution import (
    HermesExecutionConfigurationError,
    execute_hermes_run,
    mark_hermes_run_terminal_failure,
)
from open_work_hub_api.domains.hermes.publication import publish_pending_hermes_dispatches
from open_work_hub_api.domains.hermes.maintenance import maintain_headless_hermes_once


class HermesTerminalFailure(RuntimeError):
    pass


@celery_app.task(
    name=HERMES_RUN_TASK_NAME,
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    task_time_limit=3_900,
    task_soft_time_limit=3_840,
    max_retries=20,
    throws=(HermesTerminalFailure,),
)
def run_hermes_agent(self, run_id: str) -> str:
    settings = get_settings()
    if not settings.hermes_enabled:
        session = db_session()
        try:
            mark_hermes_run_terminal_failure(
                session,
                run_id=run_id,
                error_code="hermes.disabled",
                error_message="Hermes integration is disabled on this worker.",
            )
        finally:
            session.close()
        raise HermesTerminalFailure(f"hermes_disabled:{run_id}")

    session = db_session()
    try:
        result = asyncio.run(
            execute_hermes_run(
                session,
                run_id=run_id,
                runtime_base_url=settings.hermes_runtime_base_url,
                api_key=settings.hermes_api_key.get_secret_value(),
                request_timeout_seconds=settings.hermes_request_timeout_seconds,
                lease_seconds=settings.hermes_run_timeout_seconds + 300,
            )
        )
    except HermesExecutionConfigurationError as error:
        mark_hermes_run_terminal_failure(
            session,
            run_id=run_id,
            error_code="hermes.configuration_error",
            error_message=str(error),
        )
        raise HermesTerminalFailure(f"hermes_configuration_error:{run_id}") from error
    except HermesClientError as error:
        if self.request.retries >= self.max_retries - 1:
            mark_hermes_run_terminal_failure(
                session,
                run_id=run_id,
                error_code=error.code,
                error_message=str(error),
            )
            raise HermesTerminalFailure(f"hermes_terminal_failure:{run_id}") from error
        raise self.retry(exc=error, countdown=min(300, 15 * (self.request.retries + 1)))
    except SoftTimeLimitExceeded as error:
        if self.request.retries >= self.max_retries - 1:
            mark_hermes_run_terminal_failure(
                session,
                run_id=run_id,
                error_code="hermes.worker_soft_timeout",
                error_message="The Hermes worker exhausted its execution time limit.",
            )
            raise HermesTerminalFailure(f"hermes_worker_timeout:{run_id}") from error
        raise self.retry(exc=error, countdown=30)
    except Exception as error:
        if self.request.retries >= self.max_retries - 1:
            mark_hermes_run_terminal_failure(
                session,
                run_id=run_id,
                error_code="hermes.worker_unexpected",
                error_message="The Hermes worker encountered an unexpected execution error.",
            )
            raise HermesTerminalFailure(f"hermes_worker_failure:{run_id}") from error
        raise self.retry(exc=error, countdown=min(300, 15 * (self.request.retries + 1)))
    finally:
        session.close()
    if result in {"incomplete", "active_lease"}:
        raise self.retry(countdown=30)
    return result


@celery_app.task(
    name=HERMES_REPUBLISH_TASK_NAME,
    task_time_limit=120,
    task_soft_time_limit=90,
)
def republish_hermes_runs(limit: int = 100) -> int:
    asyncio.run(maintain_headless_hermes_once(limit=min(limit, 20)))
    session = db_session()
    try:
        return publish_pending_hermes_dispatches(session, limit=limit)
    finally:
        session.close()
