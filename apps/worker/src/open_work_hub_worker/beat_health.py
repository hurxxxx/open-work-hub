"""Local Beat liveness, updated only after a task reaches the broker.

This disposable marker is not task or business state. Each standalone Beat
process owns it in its working directory, alongside its Celery schedule file.
"""

import time
from pathlib import Path

from celery.signals import after_task_publish, beat_init

HEARTBEAT_FILE = Path("celerybeat-heartbeat")
MAX_AGE_SECONDS = 180


def _record_publish(**_kwargs) -> None:
    HEARTBEAT_FILE.touch(mode=0o600)


def _start_beat_health(**_kwargs) -> None:
    # A previous process must not make a new scheduler look healthy.
    HEARTBEAT_FILE.unlink(missing_ok=True)
    after_task_publish.connect(_record_publish, weak=False)


def install_beat_health() -> None:
    beat_init.connect(_start_beat_health, weak=False)


def is_healthy() -> bool:
    try:
        age = time.time() - HEARTBEAT_FILE.stat().st_mtime
    except OSError:
        return False
    return 0 <= age <= MAX_AGE_SECONDS


def main() -> int:
    if is_healthy():
        print("Beat published a task within the last 180 seconds.")
        return 0
    print("Beat has no recent successful task publication.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
