"""메일 작성 도우미 요청·응답 Pydantic 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MailTone = Literal[
    "friendly", "polite", "formal", "concise", "apologize", "report", "assertive", "technical"
]
WritingLang = Literal["ko", "en", "zh"]
TranslateTargetLang = Literal["en", "zh", "ko"]
DownloadFormat = Literal["txt", "docx", "pdf"]

# 입력 상한. 인증 사용자가 과도한 본문을 보내 LLM 호출 비용/지연이나 동기 문서
# 렌더링(메모리·CPU)으로 API 안정성을 해치지 못하도록 필드별 최대 길이를 둔다.
# 초과 시 FastAPI/Pydantic 이 422 를 반환한다.
MAX_PROMPT_INPUT = 20_000
MAX_ORIGINAL_MAIL = 50_000
MAX_TRANSLATE_SOURCE = 50_000
MAX_DOWNLOAD_CONTENT = 100_000
MAX_FILENAME = 200


class MailGenerateRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=MAX_PROMPT_INPUT, description="전달하고 싶은 내용")
    original_mail: str = Field(default="", max_length=MAX_ORIGINAL_MAIL)
    tone: MailTone = "polite"
    lang: WritingLang = "ko"


class TranslateRequest(BaseModel):
    source: str = Field(
        min_length=1, max_length=MAX_TRANSLATE_SOURCE, description="번역할 한국어 본문"
    )
    target_lang: TranslateTargetLang = "en"


class WritingResult(BaseModel):
    result: str


class DocumentDownloadRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_DOWNLOAD_CONTENT)
    format: DownloadFormat = "txt"
    filename: str = Field(default="문서", max_length=MAX_FILENAME)
