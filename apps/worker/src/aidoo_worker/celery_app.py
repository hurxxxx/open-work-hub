from celery import Celery

from aidoo_worker.settings import get_settings


settings = get_settings()

celery_app = Celery(
    "aidoo_worker",
    broker=settings.broker_url,
    backend=settings.result_backend,
)
celery_app.autodiscover_tasks(["aidoo_worker.tasks"])
