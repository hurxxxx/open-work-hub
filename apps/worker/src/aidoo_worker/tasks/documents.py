from aidoo_worker.celery_app import celery_app


@celery_app.task(name="documents.sync")
def sync_documents() -> dict[str, str]:
    return {"task": "documents.sync", "status": "scaffolded"}
