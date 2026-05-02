"""Background tasks for the worker app."""

from aidoo_worker.tasks import (  # noqa: F401
    documents,
    drafts,
    media,
    meeting,
    ocr,
    rag_sync,
    recording,
    search_index,
)
