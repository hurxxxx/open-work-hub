from aidoo_worker.celery_app import celery_app


@celery_app.task(name="ocr.normalize")
def normalize_ocr_asset() -> dict[str, str]:
    return {"task": "ocr.normalize", "status": "scaffolded"}
