"""문서 번역/요약 비즈니스 로직 — 문서 텍스트 추출 + 내부 LLM(``complete_chat``) 호출.

무상태(stateless)이며 DB 영속화가 없다. AI 챗봇의 동기식
``complete_chat`` 패턴을 따른다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import LlmTaskContext
from open_work_hub_api.domains.ai.gateway import LlmWorkloadContext, execute_llm
from open_work_hub_api.domains.document_processing.contracts import UnsupportedDocumentType
from open_work_hub_api.domains.document_processing.extractors import extract_document

from . import prompts
from .schemas import DocMode, DocProcessResult, SummaryLevel, TargetLang

TASK_KIND = "document_translate"
# LLM 컨텍스트 보호를 위한 입력 상한(원본 C:\server 와 동일).
_MAX_INPUT_CHARS = 30_000
_TRUNCATE_NOTICE = "\n\n[이하 내용 생략 - 문서가 너무 깁니다]"


class DocumentTranslateError(ValueError):
    """문서 추출 실패 등 사용자에게 노출하는 오류.

    ``code`` 는 i18n 카탈로그의 메시지 코드(``document_translate.*``)로, 라우터가
    ``localized_http_exception`` 으로 변환할 때 사용한다.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def extract_text(*, content: bytes, filename: str, mime_type: str) -> str:
    """업로드 바이트에서 텍스트를 추출한다.

    ``.txt`` 는 직접 UTF-8 디코드하고, 그 외(PDF/DOCX/XLSX/PPTX)는
    ``extract_document`` 으로 위임한다.
    """
    name = (filename or "").lower()
    if name.endswith(".txt"):
        text = content.decode("utf-8", errors="replace").strip()
    else:
        try:
            bundle = extract_document(
                document_id="doc-translate",
                filename=filename,
                mime_type=mime_type or "application/octet-stream",
                content=content,
            )
        except UnsupportedDocumentType as error:
            raise DocumentTranslateError("document_translate.unsupported_file_type") from error
        text = bundle.normalized_text.strip()

    if not text:
        raise DocumentTranslateError("document_translate.extraction_failed")
    return text


def _generate(db: Session, context: LlmTaskContext, prompt: str) -> str:
    result = execute_llm(
        context.task_kind,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[{"role": "user", "content": prompt}],
    )
    return result.completion.text


def _build_prompt(
    text: str,
    *,
    mode: DocMode,
    target_lang: TargetLang,
    summary_level: SummaryLevel,
) -> str:
    if mode == "translate":
        return prompts.build_translate_prompt(text, target_lang)
    if mode == "extract":
        return prompts.build_extract_prompt(text, target_lang)
    return prompts.build_summarize_prompt(text, summary_level, target_lang)


def process(
    db: Session,
    context: LlmTaskContext,
    *,
    text: str,
    mode: DocMode,
    target_lang: TargetLang,
    summary_level: SummaryLevel,
) -> DocProcessResult:
    """추출/입력된 텍스트를 mode 별로 처리한다."""
    cleaned = text.strip()
    if not cleaned:
        raise DocumentTranslateError("document_translate.empty_text")

    char_count = len(cleaned)
    if char_count > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS] + _TRUNCATE_NOTICE

    prompt = _build_prompt(cleaned, mode=mode, target_lang=target_lang, summary_level=summary_level)
    result = _generate(db, context, prompt)
    return DocProcessResult(result=result, mode=mode, char_count=char_count)
