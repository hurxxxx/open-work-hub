from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_alm_api.core.settings import Settings, get_settings
from open_alm_api.core.worker_queue_contract import IMAGE_GENERATION_QUEUE
from open_alm_api.domains.images.model_settings_service import (
    get_image_model_settings_snapshot,
    resolve_active_image_execution,
)
from open_alm_api.domains.images.models import ImageGeneration


class ImageModelCutoverError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ImageModelCutoverStatus:
    deployment_enabled: bool
    ready: bool
    broker_queue_count: int
    active_job_count: int

    def status_line(self) -> str:
        return (
            "status=ok"
            f" deployment_enabled={int(self.deployment_enabled)}"
            f" ready={int(self.ready)}"
            f" broker_queue_count={self.broker_queue_count}"
            f" active_job_count={self.active_job_count}"
        )


def check_image_model_cutover(
    db: Session,
    *,
    jobs_only: bool = False,
    settings: Settings | None = None,
    queue_length: Callable[[], int] | None = None,
) -> ImageModelCutoverStatus:
    resolved_settings = settings or get_settings()
    try:
        broker_queue_count = int(
            queue_length()
            if queue_length is not None
            else _broker_queue_length(resolved_settings)
        )
    except Exception as exc:
        raise ImageModelCutoverError("broker_queue_unavailable") from exc
    active_job_count = int(
        db.scalar(
            select(func.count())
            .select_from(ImageGeneration)
            .where(ImageGeneration.image_status.in_(("queued", "running")))
        )
        or 0
    )
    if broker_queue_count:
        raise ImageModelCutoverError("broker_queue_not_empty")
    if active_job_count:
        raise ImageModelCutoverError("active_jobs_present")

    if jobs_only or not resolved_settings.image_enabled:
        return ImageModelCutoverStatus(
            deployment_enabled=resolved_settings.image_enabled,
            ready=False,
            broker_queue_count=broker_queue_count,
            active_job_count=active_job_count,
        )

    snapshot = get_image_model_settings_snapshot(db, settings=resolved_settings)
    if not snapshot.ready:
        raise ImageModelCutoverError(snapshot.readiness_code or "settings_not_ready")
    try:
        resolve_active_image_execution(db, settings=resolved_settings)
    except Exception as exc:
        raise ImageModelCutoverError("execution_resolution_failed") from exc
    return ImageModelCutoverStatus(
        deployment_enabled=True,
        ready=True,
        broker_queue_count=broker_queue_count,
        active_job_count=active_job_count,
    )


def _broker_queue_length(settings: Settings) -> int:
    client = Redis.from_url(settings.worker_broker_url, socket_timeout=5)
    try:
        return int(client.llen(IMAGE_GENERATION_QUEUE))
    finally:
        client.close()


__all__ = [
    "ImageModelCutoverError",
    "ImageModelCutoverStatus",
    "check_image_model_cutover",
]
