from open_alm_worker.celery_app import celery_app


@celery_app.task(name="drafts.export")
def export_draft() -> dict[str, str]:
    return {"task": "drafts.export", "status": "scaffolded"}
