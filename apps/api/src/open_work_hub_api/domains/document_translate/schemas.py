"""문서 번역/요약 요청·응답 Pydantic 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DocMode = Literal["translate", "summarize", "extract"]
SummaryLevel = Literal["brief", "detailed"]
# 지원 대상 언어 — 원본(C:\server)과 동일.
TargetLang = Literal["ko", "en", "zh", "ja", "es", "de"]


class DocProcessTextRequest(BaseModel):
    """붙여넣은 텍스트 처리 요청."""

    text: str = Field(min_length=1)
    mode: DocMode = "summarize"
    target_lang: TargetLang = "ko"
    summary_level: SummaryLevel = "detailed"


class DocProcessResult(BaseModel):
    result: str
    mode: DocMode
    char_count: int
