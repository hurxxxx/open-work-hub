from __future__ import annotations

import sys
from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger, after_setup_task_logger, celeryd_init
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from open_work_hub_worker.settings import get_settings
from open_work_hub_worker.queue_contract import (
    AI_GRAPH_REPUBLISH_TASK_NAME,
    DEFAULT_QUEUE,
    FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME,
    assert_worker_queue_access,
    celery_task_routes,
    celery_worker_queue_argument,
    worker_bootstrap_group_requires_llm_routing,
)


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

from open_work_hub_api.core.telemetry import bootstrap_telemetry  # noqa: E402
from open_work_hub_api.core.logging_security import (  # noqa: E402
    install_sensitive_http_logging_guard,
)
from open_work_hub_api.platform_extensions import initialize_platform_extensions  # noqa: E402


settings = get_settings()
install_sensitive_http_logging_guard()


@after_setup_logger.connect
@after_setup_task_logger.connect
def _restore_sensitive_http_logging_guard(**_kwargs) -> None:
    install_sensitive_http_logging_guard()


@celeryd_init.connect
def _guard_server_managed_queues(
    sender=None,
    instance=None,
    conf=None,
    options=None,
    **_kwargs,
) -> None:
    del sender, instance, conf
    worker_options = options if isinstance(options, dict) else {}
    requested_queues = worker_options.get("queues")
    if not requested_queues:
        requested_queues = (
            celery_worker_queue_argument()
            if settings.queue_group == "all"
            else celery_worker_queue_argument(settings.queue_group)
        )
    assert_worker_queue_access(
        queue_group=settings.queue_group,
        requested_queues=requested_queues,
        env_profile=settings.env_profile,
        root=_workspace_root(),
    )
# Keep telemetry bootstrapped before task modules import RAG metric wrappers.
bootstrap_telemetry(
    service_name="open-work-hub-worker",
    enabled=settings.otel_enabled,
    enable_console_exporter=settings.otel_console_exporter,
    enable_otlp_exporter=settings.otel_otlp_exporter_enabled,
    metrics_export_interval_ms=settings.otel_metrics_export_interval_ms,
)
initialize_platform_extensions(settings)


def _assert_llm_routing_control_plane_ready() -> None:
    if not settings.postgres_dsn.strip():
        raise RuntimeError("Worker PostgreSQL DSN is not configured.")

    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            session.execute(text("SELECT provider_id FROM ai_model_provider_configs LIMIT 1")).all()
            session.execute(text("SELECT id FROM ai_model_catalog_entries LIMIT 1")).all()
            session.execute(text("SELECT workload_id FROM ai_model_route_overrides LIMIT 1")).all()
            session.execute(
                text("SELECT provider_id FROM image_model_provider_configs LIMIT 1")
            ).all()
            session.execute(text("SELECT profile_id FROM image_model_profiles LIMIT 1")).all()
    except Exception as error:
        raise RuntimeError(
            "AI model control plane is unavailable. "
            "Run API migrations before starting the worker."
        ) from error
    finally:
        engine.dispose()

if worker_bootstrap_group_requires_llm_routing(settings.queue_group):
    _assert_llm_routing_control_plane_ready()

celery_app = Celery(
    "open_work_hub_worker",
    broker=settings.broker_url,
    backend=settings.result_backend,
)
celery_app.autodiscover_tasks(["open_work_hub_worker.tasks"])
celery_app.conf.timezone = "UTC"

celery_app.conf.beat_schedule = {
    "republish-pending-ai-graph-runs": {
        "task": AI_GRAPH_REPUBLISH_TASK_NAME,
        "schedule": 60.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "cleanup-orphan-media": {
        "task": "media.cleanup_orphans",
        "schedule": 3600.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "republish-files-storage-cleanup-jobs": {
        "task": FILE_STORAGE_CLEANUP_REPUBLISH_TASK_NAME,
        "schedule": 60.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "cleanup-stale-meeting-recording-staging": {
        "task": "meeting.cleanup_stale_staging",
        "schedule": 3600.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "dispatch-due-mail-sync-jobs": {
        "task": "mail.dispatch_due_sync_jobs",
        "schedule": 60.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "republish-pending-rag-jobs": {
        "task": "rag.republish_pending_jobs",
        "schedule": 60.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
    "republish-pending-search-index-jobs": {
        "task": "search.republish_pending_index_jobs",
        "schedule": 60.0,
        "options": {"queue": DEFAULT_QUEUE},
    },
}
celery_app.conf.task_routes = celery_task_routes()
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_graceful_shutdown_timeout = 3700
