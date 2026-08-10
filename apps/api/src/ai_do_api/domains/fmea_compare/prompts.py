"""FMEA AI 분석/비교 프롬프트 — 원본(`C:\\server\\routes\\fmea.py`) 프롬프트를 그대로 포팅."""

from __future__ import annotations

AiAnalyzeMode = str  # "summary" | "improvement" | "missing"

# 로컬 LLM(Qwen 계열)이 한국어 출력에 한자(漢字)·중국어를 섞는 경향이 있어,
# 모든 프롬프트 끝에 "한자 금지" 지시를 덧붙인다. 단, 원문의 영문 기술 용어는
# 그대로 두어야 한다(HVAC UNIT, LEVER PIN 등).
_KOREAN_ONLY_DIRECTIVE = (
    "\n\n[작성 언어 규칙] 한국어로 작성하되, 한자(漢字)나 중국어 문자는 절대 사용하지 마세요. "
    "한자로 표기될 단어는 모두 한글로 쓰세요(예: '公差'→'공차', '結合'→'결합'). "
    "다만 원문에 있는 영문 용어(예: HVAC UNIT, LEVER PIN)는 영어 그대로 두어도 됩니다."
)


def _item_line(it: dict[str, str]) -> str:
    return (
        f"- 항목: {it.get('item', '')} | 고장모드: {it.get('failure_mode', '')} | "
        f"영향: {it.get('failure_effect', '')} | 원인: {it.get('failure_cause', '')} | "
        f"S={it.get('severity', '')} O={it.get('occurrence', '')} D={it.get('detection', '')} "
        f"RPN={it.get('rpn', '')} | 권고조치: {it.get('recommended_action', '')} | "
        f"조치결과: {it.get('action_result', '')}"
    )


def build_ai_analyze_prompt(items: list[dict[str, str]], mode: str) -> str:
    """요약/개선제안/누락검토 프롬프트를 생성한다. 상위 30개 항목만 사용(토큰 절약)."""
    items_text = "\n".join(_item_line(it) for it in items[:30])

    prompts = {
        "summary": f"""다음 FMEA(고장모드 영향분석) 데이터를 분석하여 전체 요약 리포트를 작성하세요.
마크다운 기호(*, **, #)를 사용하지 말고 일반 텍스트로, 구분 제목은 대괄호로 표기하세요.

[전체 현황] - 총 항목 수, RPN 분포 요약
[고위험 항목 TOP 5] - RPN 높은 순으로 항목/고장모드/RPN/현재상태
[주요 고장 유형] - 빈도 높은 고장모드 패턴
[미조치 항목] - 권고조치 대비 미완료 항목
[종합 평가] - FMEA 전체 품질 수준 평가 및 개선 방향

{items_text}""",
        "improvement": f"""다음 FMEA 데이터에서 고위험 항목(RPN 높은 순)에 대해 구체적인 개선 방안을 제시하세요.
마크다운 기호를 사용하지 말고 일반 텍스트로, 구분 제목은 대괄호로 표기하세요.

각 고위험 항목에 대해:
[항목명 - 고장모드]
  현재 상태: 현재 예방/검출 방법
  개선 제안 (예방): 추가 예방 대책
  개선 제안 (검출): 추가 검출 방법
  예상 효과: RPN 감소 예상치

{items_text}""",
        "missing": f"""다음 FMEA 데이터에서 누락되거나 보완이 필요한 부분을 찾아주세요.
마크다운 기호를 사용하지 말고 일반 텍스트로, 구분 제목은 대괄호로 표기하세요.

[누락된 고장모드] - 해당 시스템/부품에서 추가로 고려해야 할 고장모드
[불완전한 항목] - 원인/예방/검출이 누락되거나 부실한 항목
[RPN 재검토 필요] - 심각도/발생도/검출도 평가가 부적절해 보이는 항목
[추가 권고사항]

{items_text}""",
    }

    return prompts.get(mode, prompts["summary"]) + _KOREAN_ONLY_DIRECTIVE


def build_compare_prompt(
    filename_a: str,
    items_a: list[dict[str, str]],
    filename_b: str,
    items_b: list[dict[str, str]],
) -> str:
    """두 FMEA 버전 비교 프롬프트를 생성한다. 각 상위 25개 항목만 사용."""

    def _brief(it: dict[str, str]) -> str:
        return f"- {it.get('item', '')} | {it.get('failure_mode', '')} | RPN={it.get('rpn', '')}"

    text_a = "\n".join(_brief(it) for it in items_a[:25])
    text_b = "\n".join(_brief(it) for it in items_b[:25])

    return f"""두 FMEA 버전을 비교 분석하세요.
마크다운 기호를 사용하지 말고 일반 텍스트로, 구분 제목은 대괄호로 표기하세요.

[문서 A: {filename_a}]
{text_a}

[문서 B: {filename_b}]
{text_b}

다음 항목을 분석하세요:
[추가된 항목] - B에는 있지만 A에는 없는 고장모드
[삭제된 항목] - A에는 있지만 B에는 없는 고장모드
[RPN 변경] - 동일 항목의 RPN 변화 (개선/악화)
[조치 진행 현황] - 권고조치 대비 완료 현황
[종합 비교] - 전체적인 FMEA 품질 변화 평가{_KOREAN_ONLY_DIRECTIVE}"""
