"""Background tasks for the worker app."""

from open_work_hub_worker.tasks import (  # noqa: F401
    ai_graph,
    documents,
    file_storage_cleanup,
    hermes,
    mail,
    media,
    meeting,
    ocr,
    rag_sync,
    recording,
    search_index,
)
