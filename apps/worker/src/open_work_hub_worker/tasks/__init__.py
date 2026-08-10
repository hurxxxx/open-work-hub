"""Background tasks for the worker app."""

from open_work_hub_worker.tasks import (  # noqa: F401
    ai_graph,
    documents,
    drafts,
    file_storage_cleanup,
    images,
    mail,
    media,
    meeting,
    ocr,
    rag_sync,
    recording,
    search_index,
    spec_compare,
)
