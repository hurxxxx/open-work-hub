from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_alm_api.domains.images.cutover import (
    ImageModelCutoverError,
    check_image_model_cutover,
)


class _CountOnlySession:
    def __init__(self, active_job_count: int) -> None:
        self.active_job_count = active_job_count

    def scalar(self, _statement) -> int:
        return self.active_job_count


def test_image_model_cutover_rejects_active_database_jobs() -> None:
    with pytest.raises(ImageModelCutoverError) as exc_info:
        check_image_model_cutover(
            _CountOnlySession(1),  # type: ignore[arg-type]
            jobs_only=True,
            settings=SimpleNamespace(image_enabled=True),  # type: ignore[arg-type]
            queue_length=lambda: 0,
        )

    assert exc_info.value.code == "active_jobs_present"


def test_image_model_cutover_jobs_only_allows_disabled_idle_deployment() -> None:
    result = check_image_model_cutover(
        _CountOnlySession(0),  # type: ignore[arg-type]
        jobs_only=True,
        settings=SimpleNamespace(image_enabled=False),  # type: ignore[arg-type]
        queue_length=lambda: 0,
    )

    assert result.deployment_enabled is False
    assert result.ready is False
    assert result.status_line() == (
        "status=ok deployment_enabled=0 ready=0 broker_queue_count=0 active_job_count=0"
    )
