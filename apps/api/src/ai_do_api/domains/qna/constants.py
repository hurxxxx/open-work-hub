from __future__ import annotations

# RAG wiring identifiers for the Q&A corpus.
QNA_DOCUMENT_RESOURCE_TYPE = "qna_document"
QNA_DOC_SOURCE_KIND = "qna_doc"
QNA_SCOPE_KIND = "company"
QNA_COMPANY_VISIBILITY_REF = "company_public"

# QnaDocument.kind values.
QNA_KIND_UPLOAD = "upload"
QNA_KIND_NOTICE = "notice"

QNA_DEFAULT_CATEGORY = "일반"
QNA_NOTICE_CATEGORY = "주요공지사항(관리팀)"

# Uploaded document text is capped before persistence (the extractor also caps).
QNA_MAX_BODY_CHARS = 200_000
