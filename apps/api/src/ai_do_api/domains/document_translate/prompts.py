"""문서 번역/요약/핵심추출 프롬프트 빌더."""

from __future__ import annotations

# 대상 언어 표시명. 원본과 동일.
LANG_NAMES: dict[str, str] = {
    "ko": "한국어",
    "en": "영어(English)",
    "zh": "중국어(中文)",
    "ja": "일본어(日本語)",
    "es": "스페인어(Español)",
    "de": "독일어(Deutsch)",
}


def _output_contract(target_lang: str) -> str:
    """모든 처리 모드에 한 번만 적용하는 최소 출력 계약."""
    lang_name = LANG_NAMES.get(target_lang, target_lang)
    return (
        f"출력 언어: {lang_name}\n"
        "- 원문에 없는 내용을 추가하거나 추측하지 마세요.\n"
        "- 수치와 고유명사는 원문을 정확히 반영하세요."
    )


def build_translate_prompt(text: str, target_lang: str) -> str:
    output_contract = _output_contract(target_lang)
    return f"""다음 문서를 자연스럽게 번역하세요.
{output_contract}
- 기술 용어는 해당 언어에서 통용되는 표현을 사용하세요.
- 번역 결과만 출력하고, 다른 설명은 생략하세요.

[원문]
{text}"""


def build_summarize_prompt(text: str, summary_level: str, target_lang: str = "ko") -> str:
    # 요약 = '사람이 읽고 이해하는' 줄글. 수치·키워드를 단순 나열하거나 표로 뽑는 작업은
    # '핵심 추출' 기능이 담당하므로, 여기서는 의미 중심으로 서술한다(역할 분리).
    output_contract = _output_contract(target_lang)
    if summary_level == "brief":
        return f"""다음 문서를 3~5줄의 줄글로 간략하게 요약하세요.
{output_contract}
- 키워드나 수치를 단순 나열하지 말고, 문장으로 핵심 메시지를 설명하세요.

[문서 내용]
{text}"""

    return f"""다음 문서를 사람이 읽고 이해할 수 있도록 줄글 중심으로 요약하세요.
{output_contract}

## 개요
- 원문에 명시된 목적·배경·범위만 2~3문장으로 서술하고, 해당 내용이 없으면 이 섹션을 생략하세요.

## 핵심 내용
- 문서의 주요 내용과 흐름을 문단(줄글)으로 서술하세요. 단순 키워드/수치 나열이 아니라 의미가 드러나도록 풀어서 설명합니다.

## 결론 및 시사점
- 원문에 명시된 결론·판단·시사점만 서술하고, 해당 내용이 없으면 이 섹션을 생략하세요.

작성 규칙:
- 섹션 제목은 ## 으로 시작하고, 내용은 문장으로 설명하세요.
- 수치·스펙을 표로 정리하거나 항목만 뽑아내지 말고, 필요한 수치는 문장 안에서 의미와 함께 언급하세요.

[문서 내용]
{text}"""


def build_extract_prompt(text: str, target_lang: str = "ko") -> str:
    # 핵심 추출 = 다시 활용할 '구조화 데이터' 뽑기. 요약·해석·결론을 쓰지 않고, 원문의 사실만
    # 분류별 항목으로 추출한다(요약 기능과 역할 분리).
    output_contract = _output_contract(target_lang)
    return f"""다음 문서에서 다시 활용할 수 있는 핵심 정보를 추출하여 정리하세요.
{output_contract}
문장으로 요약하거나 해석·결론을 덧붙이지 말고, 원문에 있는 사실만 항목으로 뽑으세요.
마크다운 기호(*, **, #)는 사용하지 말고 일반 텍스트로 작성하세요.
아래 분류 중 해당 내용이 있는 것만 대괄호 제목으로 묶고 번호(1. 2. 3.)로 나열하세요. 해당 내용이 없는 분류는 생략합니다.

[핵심 키워드]
[주요 수치·스펙]
[날짜·일정]
[결정사항·조치(액션 아이템)]
[고유명사·대상]

[문서 내용]
{text}"""
