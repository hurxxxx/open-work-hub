"""Local-dev news collection worker.

Runs a minimal Celery worker that consumes ONLY the dedicated ``news`` queue and
runs ``news.collect_all`` via the shared service logic. It deliberately does NOT
import ``ai_do_worker.tasks`` (which would pull in heavy/ML deps and other task
modules), and it does NOT consume the shared default queue — so it never steals
other developers' tasks from the shared dev broker.

Usage (Windows):
  scripts\\dev-windows-news-worker.ps1
which loads .env.local and invokes this with the api venv python.
"""
from __future__ import annotations

import pathlib
import sys

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_API_SRC = _ROOT / "apps" / "api" / "src"
if str(_API_SRC) not in sys.path:
    sys.path.insert(0, str(_API_SRC))

from ai_do_api.core.settings import get_settings  # noqa: E402
from ai_do_api.core.worker_queue_contract import (  # noqa: E402
    NEWS_COLLECT_QUEUE,
    NEWS_COLLECT_TASK_NAME,
)
from ai_do_api.domains.news import service  # noqa: E402

settings = get_settings()
# Local-dev: optionally consume a private queue so a shared-broker worker on
# another machine cannot steal this collection task. Set AI_DO_NEWS_COLLECT_QUEUE
# in .env.local (e.g. "news-<hostname>"); empty falls back to the shared "news".
NEWS_QUEUE = settings.news_collect_queue_override or NEWS_COLLECT_QUEUE
app = Celery("ai_do_news_local", broker=settings.worker_broker_url)
app.conf.task_default_queue = NEWS_QUEUE
app.conf.task_ignore_result = True

_engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)


@app.task(name=NEWS_COLLECT_TASK_NAME)
def collect_all(force: bool = False) -> dict[str, int]:
    del force
    with Session(_engine) as db:
        return service.run_full_collection(
            db, settings.naver_client_id, settings.naver_client_secret
        )


if __name__ == "__main__":
    app.worker_main(
        [
            "worker",
            "-Q",
            NEWS_QUEUE,
            "--pool=solo",
            "--concurrency=1",
            "-n",
            "news-local@%h",
            "--loglevel=info",
        ]
    )
