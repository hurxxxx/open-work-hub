"""IMDS 책임광물 조사표 응답 계약."""

from __future__ import annotations

from pydantic import BaseModel


class ImdsRowPreview(BaseModel):
    """책임광물 가지에 포함된 행 미리보기."""

    level: int
    name: str = ""
    code: str = ""
    type: str = ""
    mineral: str = ""


class ImdsMineralCount(BaseModel):
    mineral: str
    count: int


class ImdsAnalyzeResult(BaseModel):
    """PDF 분석 미리보기 결과 (양식 작성 전)."""

    total_rows: int
    classification: dict[str, int]
    relevant_count: int
    mineral_counts: list[ImdsMineralCount]
    rows: list[ImdsRowPreview]


class ImdsMatchResult(BaseModel):
    """조사대상품목 리스트에서 OEM품번으로 찾은 머리정보 (없으면 found=False)."""

    found: bool
    car: str = ""
    end_name: str = ""
    oem: str = ""
    dcc: str = ""
