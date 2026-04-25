from __future__ import annotations

import sys
from pathlib import Path

from celery import Celery
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.orm import Session

from aidoo_worker.settings import get_settings


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[4]


def _ensure_api_src_on_path() -> None:
    api_src = _workspace_root() / "apps" / "api" / "src"
    if str(api_src) not in sys.path:
        sys.path.insert(0, str(api_src))


_ensure_api_src_on_path()

from aidoo_api.core.llm import get_llm_policy_seed_data  # noqa: E402
from aidoo_api.core.telemetry import bootstrap_telemetry  # noqa: E402


settings = get_settings()
# Keep telemetry bootstrapped before task modules import RAG metric wrappers.
bootstrap_telemetry(
    service_name="aidoo-worker",
    enabled=settings.otel_enabled,
    enable_console_exporter=settings.otel_console_exporter,
    enable_otlp_exporter=settings.otel_otlp_exporter_enabled,
    metrics_export_interval_ms=settings.otel_metrics_export_interval_ms,
)


def _assert_llm_policy_control_plane_ready() -> None:
    if not settings.postgres_dsn.strip():
        raise RuntimeError("Worker PostgreSQL DSN is not configured.")

    required_task_kinds = {
        task_kind for task_kind, _policy_mode, _description in get_llm_policy_seed_data()
    }
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            existing_kinds = set(
                session.execute(
                    text(
                        """
                        SELECT task_kind
                        FROM llm_policies
                        WHERE task_kind IN :task_kinds
                        """
                    ).bindparams(bindparam("task_kinds", expanding=True)),
                    {"task_kinds": tuple(sorted(required_task_kinds))},
                ).scalars().all()
            )
    except Exception as error:
        raise RuntimeError(
            "LLM policy control plane is unavailable. "
            "Run API migrations before starting the worker."
        ) from error
    finally:
        engine.dispose()

    missing = required_task_kinds - existing_kinds
    if missing:
        raise RuntimeError(
            "LLM policy control plane is incomplete. Missing seeded task kinds: "
            + ", ".join(sorted(missing))
        )


_assert_llm_policy_control_plane_ready()

celery_app = Celery(
    "aidoo_worker",
    broker=settings.broker_url,
    backend=settings.result_backend,
)
celery_app.autodiscover_tasks(["aidoo_worker.tasks"])

celery_app.conf.beat_schedule = {
    "cleanup-orphan-media": {
        "task": "media.cleanup_orphans",
        "schedule": 3600.0,
    },
    "cleanup-stale-meeting-recording-staging": {
        "task": "meeting.cleanup_stale_staging",
        "schedule": 3600.0,
    },
}
celery_app.conf.task_routes = {
    "meeting.transcribe": {"queue": "meeting_transcribe"},
    "meeting.summarize": {"queue": "meeting_transcribe"},
    "meeting.extract_insights": {"queue": "meeting_transcribe"},
    "meeting.generate_doc": {"queue": "meeting_transcribe"},
    "rag.sync_resource": {"queue": "rag_sync_realtime"},
    "rag.sync_backfill_resource": {"queue": "rag_sync_backfill"},
    "rag.recompute_visibility": {"queue": "rag_visibility_recompute"},
    "search.index_resource": {"queue": "search_index_realtime"},
}
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_graceful_shutdown_timeout = 1200
