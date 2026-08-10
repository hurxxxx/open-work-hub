"""Local-dev industry-report collection worker (+ optional embedded beat).

Mirrors ``news_local_worker.py``: runs a minimal Celery worker that consumes
ONLY the dedicated ``news`` queue (which ``industry_report`` shares) against the
shared dev broker and runs ``industry_report.collect_all`` via the shared
service logic. It deliberately does NOT import ``open_alm_worker.tasks`` (heavy/ML
deps) and never consumes the shared default queue.

The production daily schedule lives in ``apps/worker/.../celery_app.py``
(06:30 cron). For LOCAL verification you can enable an embedded beat with a short
interval by setting ``IR_LOCAL_BEAT_SECONDS`` (e.g. ``60``); leave it unset to run
the worker only and trigger collection on demand via ``POST
/api/v1/industry-report/fetch``.

Honors ``OPEN_ALM_INDUSTRY_REPORT_CRAWL_ENABLED`` exactly like the real task: when
disabled, ``collect_all`` returns ``{"status": "disabled"}`` without crawling.

Usage (Windows):
  scripts\\dev-windows-industry-report-worker.ps1
which loads .env.local and invokes this with the api venv python.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_API_SRC = _ROOT / "apps" / "api" / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from open_alm_api.core.settings import get_settings  # noqa: E402
from open_alm_api.core.worker_queue_contract import (  # noqa: E402
    INDUSTRY_REPORT_COLLECT_QUEUE,
    INDUSTRY_REPORT_COLLECT_TASK_NAME,
)
from open_alm_api.domains.industry_report import service  # noqa: E402

settings = get_settings()
app = Celery("open_alm_industry_report_local", broker=settings.worker_broker_url)
app.conf.task_default_queue = INDUSTRY_REPORT_COLLECT_QUEUE
app.conf.task_ignore_result = True

_engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)


@app.task(name=INDUSTRY_REPORT_COLLECT_TASK_NAME)
def collect_all(force: bool = False) -> dict:
    if not settings.industry_report_crawl_enabled and not force:
        return {"status": "disabled"}
    with Session(_engine) as db:
        return service.run_full_collection(db)


# Beat schedule for the ``beat`` mode. Production uses the 06:30 cron in
# ``apps/worker/.../celery_app.py``; here the interval comes from
# ``IR_LOCAL_BEAT_SECONDS`` so local verification doesn't wait for the cron.
_beat_seconds = float(os.environ.get("IR_LOCAL_BEAT_SECONDS", "60") or "60")
app.conf.beat_schedule = {
    "collect-industry-report-local": {
        "task": INDUSTRY_REPORT_COLLECT_TASK_NAME,
        "schedule": _beat_seconds,
        "options": {"queue": INDUSTRY_REPORT_COLLECT_QUEUE},
    }
}


def _main() -> None:
    # Celery on Windows cannot embed beat (``-B``); run ``beat`` as its own
    # process. First CLI arg selects the mode (default: worker).
    mode = sys.argv[1] if len(sys.argv) > 1 else "worker"
    if mode == "beat":
        app.start(
            argv=[
                "beat",
                "--loglevel=info",
                "-s",
                os.path.join(tempfile.gettempdir(), "ir-celerybeat-schedule"),
            ]
        )
    else:
        app.worker_main(
            [
                "worker",
                "-Q",
                INDUSTRY_REPORT_COLLECT_QUEUE,
                "--pool=solo",
                "--concurrency=1",
                "-n",
                "industry-report-local@%h",
                "--loglevel=info",
            ]
        )


if __name__ == "__main__":
    _main()
