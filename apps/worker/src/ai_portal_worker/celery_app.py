from celery import Celery

from ai_portal_worker.settings import get_settings


settings = get_settings()

celery_app = Celery(
    "doowon_ai_portal_worker",
    broker=settings.broker_url,
    backend=settings.result_backend,
)
celery_app.autodiscover_tasks(["ai_portal_worker.tasks"])
