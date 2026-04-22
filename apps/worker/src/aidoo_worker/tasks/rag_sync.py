from __future__ import annotations

import logging

from aidoo_worker.celery_app import celery_app
from aidoo_worker.settings import get_settings


logger = logging.getLogger(__name__)


@celery_app.task(
    name="rag.sync_resource",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_resource(self, job_id: str) -> str:
    if not get_settings().rag_enabled:
        logger.info("Skipping RAG resource sync because RAG is disabled: %s", job_id)
        return "disabled"
    logger.info("RAG resource sync scaffold invoked: %s", job_id)
    return "pending-implementation"


@celery_app.task(
    name="rag.sync_backfill_resource",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_backfill_resource(self, job_id: str) -> str:
    if not get_settings().rag_enabled:
        logger.info("Skipping RAG backfill sync because RAG is disabled: %s", job_id)
        return "disabled"
    logger.info("RAG backfill sync scaffold invoked: %s", job_id)
    return "pending-implementation"


@celery_app.task(
    name="rag.recompute_visibility",
    bind=True,
    acks_late=True,
    max_retries=3,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def recompute_visibility(self, job_id: str) -> str:
    if not get_settings().rag_enabled:
        logger.info("Skipping RAG visibility recompute because RAG is disabled: %s", job_id)
        return "disabled"
    logger.info("RAG visibility recompute scaffold invoked: %s", job_id)
    return "pending-implementation"
