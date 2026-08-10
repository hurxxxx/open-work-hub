from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from celery import Celery

from open_alm_api.core.settings import get_settings
from open_alm_api.core.worker_queue_contract import (
    PATENT_PRIOR_ART_QUEUE,
    PATENT_PRIOR_ART_RUN_JOB_TASK_NAME,
)
from open_alm_api.core.worker_task_publisher import create_fail_fast_celery_publisher


class PatentPriorArtTaskPublisher(Protocol):
    def send_task(
        self,
        name: str,
        *,
        args: list[str],
        queue: str,
        task_id: str,
    ) -> object: ...


@dataclass(frozen=True)
class PatentPriorArtJobDispatcher:
    publisher: PatentPriorArtTaskPublisher
    task_name: str = PATENT_PRIOR_ART_RUN_JOB_TASK_NAME
    queue: str = PATENT_PRIOR_ART_QUEUE

    def dispatch(self, job_id: str, *, task_id: str) -> None:
        self.publisher.send_task(
            self.task_name,
            args=[job_id],
            queue=self.queue,
            task_id=task_id,
        )


def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_alm_patent_prior_art",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def patent_prior_art_job_dispatcher() -> PatentPriorArtJobDispatcher:
    return PatentPriorArtJobDispatcher(publisher=get_celery_client())


__all__ = [
    "PatentPriorArtJobDispatcher",
    "PatentPriorArtTaskPublisher",
    "patent_prior_art_job_dispatcher",
]
