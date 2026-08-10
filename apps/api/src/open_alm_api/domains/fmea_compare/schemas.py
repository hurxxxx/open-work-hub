"""FMEA 비교/분석 요청·응답 Pydantic 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FmeaItem(BaseModel):
    """추출된 FMEA 단일 항목. 원본 키를 그대로 노출한다(누락 키는 빈 문자열)."""

    item: str = ""
    failure_mode: str = ""
    failure_effect: str = ""
    failure_cause: str = ""
    classification: str = ""
    severity: str = ""
    occurrence: str = ""
    detection: str = ""
    rpn: str = ""
    prevention: str = ""
    detection_method: str = ""
    recommended_action: str = ""
    action_result: str = ""
    action_date: str = ""


class FmeaStats(BaseModel):
    total: int = 0
    avg_rpn: float = 0
    max_rpn: int = 0
    high_risk_count: int = 0
    no_action_count: int = 0


class FmeaAnalyzeResult(BaseModel):
    filename: str
    total: int
    stats: FmeaStats
    items: list[FmeaItem]
    high_risk: list[FmeaItem]
    no_action: list[FmeaItem]


class FmeaAiAnalyzeRequest(BaseModel):
    items: list[FmeaItem] = Field(default_factory=list)
    mode: Literal["summary", "improvement", "missing"] = "summary"


class FmeaAiAnalyzeResult(BaseModel):
    result: str
    mode: str


class FmeaCompareFileInfo(BaseModel):
    filename: str
    count: int


class FmeaCompareResult(BaseModel):
    comparison: str
    file_a: FmeaCompareFileInfo
    file_b: FmeaCompareFileInfo
