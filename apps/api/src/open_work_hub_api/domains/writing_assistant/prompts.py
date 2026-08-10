"""메일 작성 프롬프트.

원본은 외부 Claude 를 썼지만 Open Work Hub 는 기본적으로 로컬 LLM(Qwen 계열)을 쓴다. 로컬 LLM 이
한국어 출력에 한자(漢字)·중국어를 섞는 경향이 있어, 한국어(``lang == "ko"``) 출력에는
``_KOREAN_ONLY_DIRECTIVE`` 를 덧붙인다.
"""

from __future__ import annotations

# 메일 어투.
MAIL_TONE_PROMPTS: dict[str, str] = {
    "friendly": "친근하고 따뜻한 말투로, 이모지를 적절히 사용하여",
    "polite": "공손하고 정중한 말투로, 격식을 갖추어",
    "formal": "격식체를 사용하여 매우 공식적이고 비즈니스적으로",
    "concise": "간결하고 핵심만 담아 짧게",
    "apologize": "진심 어린 사과가 충분히 전달되도록, 실수나 지연에 대해 정중하고 진지하게",
    "report": "상사에게 업무를 보고하는 형식으로, 요점과 진행 상황을 명확하게 정리하여",
    "assertive": "감정적이지 않고 논리적으로, 입장을 명확하고 단호하게",
    "technical": "전문 기술 서신 형식으로, 사양·품질·납기 관련 용어를 적절히 사용하여 명확하고 체계적으로",
}

_LANG_NAMES: dict[str, str] = {
    "ko": "한국어",
    "en": "영어(English)",
    "zh": "중국어(中文)",
}

_KOREAN_ONLY_DIRECTIVE = (
    "\n\n[작성 언어 규칙] 한국어로 작성하되, 한자(漢字)나 중국어 문자는 절대 사용하지 마세요. "
    "한자로 표기될 단어는 모두 한글로 쓰세요(예: '公差'→'공차', '結合'→'결합'). "
    "다만 회사명·제품명 등 원문에 있는 영문 용어는 영어 그대로 두어도 됩니다."
)

# 외국어 출력의 "[한국어 번역 / 참고용]" 블록 전용 규칙. 로컬 LLM 이 한국어 번역에
# 한자/중국어(예: '盘点')를 그대로 남기는 경향이 있어, 번역문은 순수 한글로 강제한다.
_KO_TRANSLATION_ONLY_DIRECTIVE = (
    "\n\n[한국어 번역 작성 규칙] '[한국어 번역 / 참고용]' 이후의 번역문은 반드시 한글로만 작성하세요. "
    "한자(漢字/汉字)나 중국어 문자를 단 하나도 포함하지 말고, 그런 단어는 모두 한글로 옮기세요"
    "(예: '盘点'→'재고조사', '请求'→'요청', '公差'→'공차'). "
    "숫자와 회사명·제품명 등 영문 고유명사는 그대로 두어도 됩니다."
)


def build_translate_prompt(source: str, target_lang: str) -> str:
    """본문을 대상 언어로 재번역하는 프롬프트. 원본 mailwriter.py translate 와 동일.

    양방향으로 쓴다:
    - 한국어(참고) 번역을 수정하면 그 한국어를 외국어로 번역해 왼쪽 원문을 갱신한다.
    - 외국어 결과물을 직접 수정하면 그 외국어를 한국어로 번역해 오른쪽 참고 번역을 갱신한다.
    """
    if target_lang == "ko":
        return (
            f"""다음 비즈니스 문서를 자연스러운 한국어 비즈니스 문체로 번역해주세요.
동일한 구조(제목/타이틀, 인사말, 본문 단락, 맺음말)와 동일한 격식 수준을 유지하세요.
원문이 대괄호로 섹션 제목을 표기하면 한국어에서도 대괄호를 사용하세요. 예: [제목], [본문].
평문만 사용하세요 — 마크다운 기호(*, **, #)를 쓰지 마세요.
번역된 한국어 문서만 출력하세요. 설명이나 원문은 출력하지 마세요.

[원문]
{source}"""
            + _KOREAN_ONLY_DIRECTIVE
        )

    if target_lang == "zh":
        return f"""请将下面的韩语商务文档翻译成正式的商务简体中文。
保持相同的结构(标题、问候、正文段落、结尾)和相同的正式程度。
仅使用纯文本 - 不要使用 Markdown 符号(*, **, #)。
只输出翻译后的中文文档。不要任何说明,不要韩语文本。

[韩语原文]
{source}"""

    return f"""Translate the following Korean business document into formal business English.
Keep the same structure (subject/title, greeting, body paragraphs, closing) and the same formality level.
Use square brackets for section titles if the source uses them. Example: [Title], [Body].
Use plain text only — no markdown symbols (*, **, #).
Output ONLY the translated English document. No explanations, no Korean text.

[Korean Original]
{source}"""


def build_mail_prompt(original_mail: str, intent: str, tone: str, lang: str) -> str:
    """업무 메일 작성 프롬프트를 생성한다."""
    tone_desc = MAIL_TONE_PROMPTS.get(tone, MAIL_TONE_PROMPTS["polite"])
    lang_name = _LANG_NAMES.get(lang, "한국어")
    original_section = f"\n[받은 메일]\n{original_mail}\n" if original_mail else ""

    if lang == "ko":
        output_rule = "메일 본문만 출력하고, 다른 설명은 생략해주세요."
    else:
        output_rule = (
            "출력 형식 (반드시 이 순서를 지켜주세요):\n"
            f"  1) {lang_name}로 작성한 메일 전체 (제목 + 본문 + 마무리 인사)\n"
            '  2) 빈 줄과 "---" 구분선\n'
            '  3) 빈 줄과 "[한국어 번역 / 참고용]" 헤더\n'
            "  4) 위 메일 전체의 자연스러운 한국어 번역 (작성자가 내용을 검토할 수 있도록)\n"
            '중요: 구분선 "---" 과 헤더 "[한국어 번역 / 참고용]" 은 반드시 평문으로만 출력하세요. '
            "마크다운 볼드(**), 이탤릭(*), 백틱(`), 기타 장식 기호를 헤더나 구분선에 절대 붙이지 마세요. "
            "그 외 다른 설명·주석은 절대 출력하지 마세요."
        )

    prompt = f"""아래 내용을 바탕으로 메일을 작성해주세요.
{original_section}
[전달하고 싶은 내용]
{intent}

작성 규칙:
- {tone_desc} 작성해주세요.
- 제목(Subject)도 함께 작성해주세요.
- 인사말, 본문, 마무리 인사 순서로 작성해주세요.
- 메일 본문은 반드시 {lang_name}로 작성해주세요.
- {output_rule}"""

    if lang == "ko":
        return prompt + _KOREAN_ONLY_DIRECTIVE
    return prompt + _KO_TRANSLATION_ONLY_DIRECTIVE
