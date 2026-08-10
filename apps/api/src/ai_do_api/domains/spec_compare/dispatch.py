from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from celery import Celery

from ai_do_api.core.settings import get_settings
from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from ai_do_api.core.worker_queue_contract import (
    SPEC_COMPARE_QUEUE,
    SPEC_COMPARE_RUN_JOB_TASK_NAME,
)


RUN_JOB_TASK_NAME = SPEC_COMPARE_RUN_JOB_TASK_NAME
RUN_JOB_QUEUE = SPEC_COMPARE_QUEUE


class SpecCompareTaskPublisher(Protocol):
    def send_task(self, name: str, *, args: list[str], queue: str) -> object: ...


@dataclass(frozen=True)
class SpecCompareJobDispatcher:
    publisher: SpecCompareTaskPublisher
    task_name: str = RUN_JOB_TASK_NAME
    queue: str = RUN_JOB_QUEUE

    def dispatch(self, job_id: str) -> str | None:
        async_result = self.publisher.send_task(
            self.task_name,
            args=[job_id],
            queue=self.queue,
        )
        return getattr(async_result, "id", None)


def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "ai_do_spec_compare",
        broker=settings.worker_broker_url,
        ignore_result=True,
    )


def spec_compare_job_dispatcher() -> SpecCompareJobDispatcher:
    return SpecCompareJobDispatcher(publisher=get_celery_client())
