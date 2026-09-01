from __future__ import annotations

import asyncio

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.queue_contract import HERMES_TERMINAL_MAINTENANCE_TASK_NAME

from open_work_hub_api.domains.hermes_terminal.maintenance import (
    maintain_hermes_terminal_once,
)


@celery_app.task(
    name=HERMES_TERMINAL_MAINTENANCE_TASK_NAME,
    task_time_limit=900,
    task_soft_time_limit=840,
)
def maintain_hermes_terminal_sessions(limit: int = 20) -> dict[str, int]:
    return asyncio.run(maintain_hermes_terminal_once(limit=limit))
