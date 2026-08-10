"""Background tasks for the worker app."""

from open_alm_worker.tasks import (  # noqa: F401
    ai_graph,
    documents,
    drafts,
    file_storage_cleanup,
    hr,
    images,
    industry_report,
    legacy_issue_attachment_index,
    mail,
    media,
    meeting,
    news_aggregator,
    ocr,
    ppt_generator,
    qna_board,
    rag_sync,
    recording,
    search_index,
    spec_compare,
)
from open_alm_worker.tasks.apps.legacy_issues import excel_export  # noqa: F401,E402
from open_alm_worker.tasks.apps import patent_prior_art  # noqa: F401,E402
