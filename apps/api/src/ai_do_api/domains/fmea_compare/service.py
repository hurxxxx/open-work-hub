"""FMEA 분석/비교 비즈니스 로직 — 엑셀 파싱 + 내부 LLM(``complete_chat``) 호출.

무상태(stateless)이며 DB 영속화가 없다. AI 챗봇(``domains/ai/router.py``)의 동기식
``complete_chat`` 패턴을 따른다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.core.llm import LlmTaskContext
from ai_do_api.domains.ai.gateway import LlmWorkloadContext, execute_llm

from . import prompts
from .excel import (
    FmeaParseError,
    detect_fmea_columns,
    extract_fmea_items,
    parse_fmea_excel,
)
from .schemas import (
    FmeaAiAnalyzeResult,
    FmeaAnalyzeResult,
    FmeaCompareFileInfo,
    FmeaCompareResult,
    FmeaItem,
    FmeaStats,
)

TASK_KIND = "fmea_compare"
_EMPTY_ACTION_TOKENS = ("-", "N/A", "없음", "")


def _parse_items(content: bytes, filename: str) -> list[dict[str, str]]:
    rows = parse_fmea_excel(content, filename)
    col_map = detect_fmea_columns(rows)
    return extract_fmea_items(rows, col_map)


def analyze(content: bytes, filename: str) -> FmeaAnalyzeResult:
    """FMEA 파일을 파싱해 통계와 리스크 항목 목록을 계산한다(LLM 미사용)."""
    items = _parse_items(content, filename)
    if not items:
        raise FmeaParseError("FMEA 데이터를 인식할 수 없습니다. 헤더 형식을 확인하세요.")

    rpn_values: list[int] = []
    high_risk: list[dict[str, str]] = []
    no_action: list[dict[str, str]] = []

    for item in items:
        rpn = 0
        try:
            rpn = int(float(item.get("rpn", "0") or "0"))
            rpn_values.append(rpn)
            if rpn >= 100:
                high_risk.append(item)
        except (ValueError, TypeError):
            pass

        action = item.get("recommended_action", "").strip()
        result = item.get("action_result", "").strip()
        has_action_needed = action and action not in _EMPTY_ACTION_TOKENS
        has_result = result and result not in _EMPTY_ACTION_TOKENS
        if has_action_needed and not has_result:
            no_action.append(item)
        elif rpn >= 50 and not has_result and not has_action_needed:
            # RPN 이 높은데 아무 조치 계획도 없는 항목도 미조치로 포함
            no_action.append(item)

    high_risk.sort(key=lambda x: int(float(x.get("rpn", "0") or "0")), reverse=True)

    total = len(items)
    stats = FmeaStats(
        total=total,
        avg_rpn=round(sum(rpn_values) / len(rpn_values), 1) if rpn_values else 0,
        max_rpn=max(rpn_values) if rpn_values else 0,
        high_risk_count=len(high_risk),
        no_action_count=len(no_action),
    )

    return FmeaAnalyzeResult(
        filename=filename,
        total=total,
        stats=stats,
        items=[FmeaItem(**it) for it in items[:200]],
        high_risk=[FmeaItem(**it) for it in high_risk[:20]],
        no_action=[FmeaItem(**it) for it in no_action[:20]],
    )


def _generate(db: Session, context: LlmTaskContext, prompt: str) -> str:
    result = execute_llm(
        context.task_kind,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[{"role": "user", "content": prompt}],
    )
    return result.completion.text


def ai_analyze(
    db: Session,
    context: LlmTaskContext,
    *,
    items: list[FmeaItem],
    mode: str,
) -> FmeaAiAnalyzeResult:
    """요약/개선제안/누락검토 AI 분석을 수행한다."""
    item_dicts = [it.model_dump() for it in items]
    prompt = prompts.build_ai_analyze_prompt(item_dicts, mode)
    result = _generate(db, context, prompt)
    return FmeaAiAnalyzeResult(result=result, mode=mode)


def compare(
    db: Session,
    context: LlmTaskContext,
    *,
    content_a: bytes,
    filename_a: str,
    content_b: bytes,
    filename_b: str,
) -> FmeaCompareResult:
    """두 FMEA 파일을 파싱하고 AI 로 버전 차이를 비교한다."""
    items_a = _parse_items(content_a, filename_a)
    items_b = _parse_items(content_b, filename_b)

    prompt = prompts.build_compare_prompt(filename_a, items_a, filename_b, items_b)
    comparison = _generate(db, context, prompt)

    return FmeaCompareResult(
        comparison=comparison,
        file_a=FmeaCompareFileInfo(filename=filename_a, count=len(items_a)),
        file_b=FmeaCompareFileInfo(filename=filename_b, count=len(items_b)),
    )
