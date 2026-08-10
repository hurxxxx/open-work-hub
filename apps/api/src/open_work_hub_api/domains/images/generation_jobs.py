from __future__ import annotations

from functools import lru_cache

from celery import Celery

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_work_hub_api.core.worker_queue_contract import (
    IMAGE_GENERATION_QUEUE,
    IMAGE_GENERATION_TASK_NAME,
)


GENERATE_IMAGE_TASK_NAME = IMAGE_GENERATION_TASK_NAME


@lru_cache(maxsize=1)
def get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_work_hub_api_images",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


def dispatch_image_generation(generation_id: str) -> str | None:
    async_result = get_celery_client().send_task(
        GENERATE_IMAGE_TASK_NAME,
        args=[generation_id],
        queue=IMAGE_GENERATION_QUEUE,
    )
    return getattr(async_result, "id", None)


def revoke_image_generation(task_id: str) -> None:
    get_celery_client().control.revoke(task_id, terminate=False)
