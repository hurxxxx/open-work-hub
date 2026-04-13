from celery import Celery

from aidoo_worker.settings import get_settings


settings = get_settings()

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
    "meeting.generate_doc": {"queue": "meeting_transcribe"},
}
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_graceful_shutdown_timeout = 1200
