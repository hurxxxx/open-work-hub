from __future__ import annotations

from ai_do_worker.celery_app import celery_app
from ai_do_worker.queue_contract import (
    AI_GRAPH_REPUBLISH_TASK_NAME,
    AI_GRAPH_RUN_TASK_NAME,
)
from ai_do_worker.runtime import db_session as _db_session

from ai_do_api.domains.ai_graph.execution_registry import execute_registered_ai_graph
from ai_do_api.domains.ai_graph.publication import publish_pending_graph_dispatches


_RETRYABLE_EXECUTION_RESULTS = frozenset(
    {"active_lease", "already_running", "lease_lost"}
)


class AiGraphTerminalFailure(RuntimeError):
    """Celery task marker for a graph already persisted as terminally failed."""


@celery_app.task(
    name=AI_GRAPH_RUN_TASK_NAME,
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
    task_time_limit=1_200,
    task_soft_time_limit=1_170,
    max_retries=None,
    throws=(AiGraphTerminalFailure,),
)
def run_ai_graph(_self, run_id: str) -> str:
    result = execute_registered_ai_graph(run_id)
    if result in _RETRYABLE_EXECUTION_RESULTS:
        raise _self.retry(countdown=60)
    if result == "failed":
        raise AiGraphTerminalFailure(f"ai_graph_terminal_failure:{run_id}")
    return result


@celery_app.task(
    name=AI_GRAPH_REPUBLISH_TASK_NAME,
    task_time_limit=120,
    task_soft_time_limit=90,
)
def republish_ai_graph_runs(limit: int = 100) -> int:
    session = _db_session()
    try:
        return publish_pending_graph_dispatches(session, limit=limit)
    finally:
        session.close()
