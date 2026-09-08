from __future__ import annotations

import os
import time

from celery import Celery
from celery.signals import after_task_publish, beat_init
import pytest

from open_work_hub_worker import beat_health


@pytest.fixture
def heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "celerybeat-heartbeat"
    monkeypatch.setattr(beat_health, "HEARTBEAT_FILE", path)
    after_task_publish.disconnect(beat_health._record_publish)
    beat_health.install_beat_health()
    yield path
    after_task_publish.disconnect(beat_health._record_publish)
    beat_init.disconnect(beat_health._start_beat_health)


def test_only_started_beat_records_successful_publication(heartbeat) -> None:
    with Celery("beat-health-test", broker="memory://") as app:
        app.send_task("maintenance", ignore_result=True)
        assert not heartbeat.exists()

        heartbeat.touch()
        beat_init.send(sender=object())
        assert not beat_health.is_healthy()

        app.send_task("maintenance", ignore_result=True)
        assert beat_health.is_healthy()


def test_failed_publish_does_not_refresh_heartbeat(heartbeat, monkeypatch) -> None:
    beat_init.send(sender=object())
    heartbeat.touch()
    stale = time.time() - beat_health.MAX_AGE_SECONDS - 1
    os.utime(heartbeat, (stale, stale))

    with Celery("beat-health-failure-test", broker="memory://") as app:
        with app.producer_pool.acquire(block=True) as producer:

            def fail(*_args, **_kwargs):
                raise ConnectionError("broker unavailable")

            monkeypatch.setattr(producer, "publish", fail)
            with pytest.raises(ConnectionError):
                app.send_task("maintenance", producer=producer, ignore_result=True)

    assert heartbeat.stat().st_mtime == stale
    assert not beat_health.is_healthy()
    assert beat_health.main() == 1


def test_missing_stale_and_future_markers_are_unhealthy(heartbeat) -> None:
    assert not beat_health.is_healthy()
    heartbeat.touch()
    assert beat_health.main() == 0
    for offset in (-beat_health.MAX_AGE_SECONDS - 1, 60):
        timestamp = time.time() + offset
        os.utime(heartbeat, (timestamp, timestamp))
        assert not beat_health.is_healthy()
