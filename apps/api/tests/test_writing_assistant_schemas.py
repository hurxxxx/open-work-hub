"""기안/메일 작성 도우미 입력 크기 상한(max_length) 계약 테스트.

인증 사용자가 과도한 본문을 보내 LLM 호출 비용/지연이나 동기 문서 렌더링으로
API 안정성을 해치지 못하도록, 요청 스키마는 필드별 최대 길이를 강제하고 초과 시
``ValidationError`` (FastAPI 경유 시 422) 를 낸다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_alm_api.domains.writing_assistant.schemas import (
    MAX_DOWNLOAD_CONTENT,
    MAX_FILENAME,
    MAX_ORIGINAL_MAIL,
    MAX_PROMPT_INPUT,
    MAX_TRANSLATE_SOURCE,
    DocumentDownloadRequest,
    DraftGenerateRequest,
    MailGenerateRequest,
    TranslateRequest,
)


def test_draft_request_accepts_max_and_rejects_over_limit() -> None:
    assert DraftGenerateRequest(text="x" * MAX_PROMPT_INPUT).text
    with pytest.raises(ValidationError):
        DraftGenerateRequest(text="x" * (MAX_PROMPT_INPUT + 1))


def test_mail_request_enforces_intent_and_original_mail_limits() -> None:
    assert MailGenerateRequest(
        intent="x" * MAX_PROMPT_INPUT,
        original_mail="y" * MAX_ORIGINAL_MAIL,
    )
    with pytest.raises(ValidationError):
        MailGenerateRequest(intent="x" * (MAX_PROMPT_INPUT + 1))
    with pytest.raises(ValidationError):
        MailGenerateRequest(intent="ok", original_mail="y" * (MAX_ORIGINAL_MAIL + 1))


def test_translate_request_rejects_oversized_source() -> None:
    assert TranslateRequest(source="x" * MAX_TRANSLATE_SOURCE)
    with pytest.raises(ValidationError):
        TranslateRequest(source="x" * (MAX_TRANSLATE_SOURCE + 1))


def test_download_request_enforces_content_and_filename_limits() -> None:
    assert DocumentDownloadRequest(
        content="x" * MAX_DOWNLOAD_CONTENT,
        filename="f" * MAX_FILENAME,
    )
    with pytest.raises(ValidationError):
        DocumentDownloadRequest(content="x" * (MAX_DOWNLOAD_CONTENT + 1))
    with pytest.raises(ValidationError):
        DocumentDownloadRequest(content="ok", filename="f" * (MAX_FILENAME + 1))


def test_required_fields_reject_empty() -> None:
    with pytest.raises(ValidationError):
        DraftGenerateRequest(text="")
    with pytest.raises(ValidationError):
        MailGenerateRequest(intent="")
    with pytest.raises(ValidationError):
        TranslateRequest(source="")
    with pytest.raises(ValidationError):
        DocumentDownloadRequest(content="")
