from celery import Celery


celery_app = Celery(
    "doowon_ai_portal_worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)
celery_app.autodiscover_tasks(["ai_portal_worker.tasks"])
