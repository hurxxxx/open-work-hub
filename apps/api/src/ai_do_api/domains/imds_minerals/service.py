"""IMDS 책임광물 조사표 비즈니스 로직 — PDF 파싱 + 엑셀 양식 작성.

무상태(stateless)이며 DB 영속화·LLM 호출이 없는 순수 변환 도메인이다. 입력 바이트를
받아 분석 결과(JSON) 또는 작성된 엑셀 바이트를 돌려준다.
"""

from __future__ import annotations

from collections import Counter

from .parser import ImdsParseError, ParsedImds, analyze as parse_pdf, get_mineral
from .schemas import ImdsAnalyzeResult, ImdsMatchResult, ImdsMineralCount, ImdsRowPreview
from .target_list import ImdsListError, match_oem
from .workbook import (
    ImdsMeta,
    ImdsSheetNotFoundError,
    ImdsTemplateError,
    ImdsWorkbookError,
    write_workbook,
)

# 미리보기 응답에 포함할 책임광물 가지 행 최대 수.
_PREVIEW_ROW_LIMIT = 20

__all__ = [
    "ImdsParseError",
    "ImdsWorkbookError",
    "ImdsTemplateError",
    "ImdsSheetNotFoundError",
    "ImdsListError",
    "ImdsMeta",
    "analyze",
    "generate",
    "match_metadata",
]


def _mineral_counts(parsed: ParsedImds) -> list[ImdsMineralCount]:
    counter: Counter[str] = Counter()
    for idx in parsed.relevant:
        row = parsed.rows[idx]
        if row["type"] == "chemical":
            mineral = get_mineral(row)
            if mineral:
                counter[mineral] += 1
    return [ImdsMineralCount(mineral=name, count=count) for name, count in counter.most_common()]


def analyze(content: bytes) -> ImdsAnalyzeResult:
    """PDF 를 파싱해 분류 통계·검출 광물·책임광물 가지 미리보기를 돌려준다."""
    parsed = parse_pdf(content)
    classification = dict(Counter(r["type"] for r in parsed.rows))
    preview = [
        ImdsRowPreview(
            level=parsed.rows[idx]["level"],
            name=parsed.rows[idx]["name"],
            code=parsed.rows[idx]["code"],
            type=parsed.rows[idx]["type"],
            mineral=get_mineral(parsed.rows[idx]) or "",
        )
        for idx in parsed.relevant[:_PREVIEW_ROW_LIMIT]
    ]
    return ImdsAnalyzeResult(
        total_rows=len(parsed.rows),
        classification=classification,
        relevant_count=len(parsed.relevant),
        mineral_counts=_mineral_counts(parsed),
        rows=preview,
    )


def generate(content: bytes, template: bytes, sheet: str, meta: ImdsMeta) -> tuple[bytes, int]:
    """PDF + 양식 엑셀로 책임광물 조사표를 작성하고 (엑셀 바이트, 기록 행수)를 돌려준다."""
    parsed = parse_pdf(content)
    return write_workbook(template, sheet, parsed.rows, parsed.relevant, meta)


def match_metadata(list_content: bytes, oem: str) -> ImdsMatchResult:
    """조사대상품목 리스트에서 OEM품번으로 차종/품명/DCC품번을 찾는다."""
    row = match_oem(list_content, oem)
    if not row:
        return ImdsMatchResult(found=False, oem=oem.strip())
    return ImdsMatchResult(
        found=True,
        car=row["car"],
        end_name=row["end_name"],
        oem=row["oem"],
        dcc=row["dcc"],
    )
