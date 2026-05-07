"""Background tasks for the worker app."""

from ai_do_worker.tasks import (  # noqa: F401
    documents,
    drafts,
    images,
    media,
    meeting,
    ocr,
    rag_sync,
    recording,
    search_index,
)
