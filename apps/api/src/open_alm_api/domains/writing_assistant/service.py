"""기안/메일 작성 비즈니스 로직 — 내부 LLM(``complete_chat``) 호출.

무상태이며 DB 영속화가 없다. FMEA 도우미와 동일하게 AI 챗봇의 동기식
``complete_chat`` 패턴을 따른다.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import LlmWorkloadContext, execute_llm

from . import prompts
from .schemas import WritingResult

DRAFT_TASK_KIND = "draft_assist"
MAIL_TASK_KIND = "mail_compose"
TRANSLATE_TASK_KIND = "writing_translate"


def _generate(db: Session, context: LlmTaskContext, prompt: str) -> str:
    result = execute_llm(
        context.task_kind,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[{"role": "user", "content": prompt}],
    )
    return result.completion.text


def generate_draft(
    db: Session,
    context: LlmTaskContext,
    *,
    text: str,
    draft_type: str,
    lang: str,
) -> WritingResult:
    prompt = prompts.build_draft_prompt(text, draft_type, lang)
    return WritingResult(result=_generate(db, context, prompt))


def generate_mail(
    db: Session,
    context: LlmTaskContext,
    *,
    intent: str,
    original_mail: str,
    tone: str,
    lang: str,
) -> WritingResult:
    prompt = prompts.build_mail_prompt(original_mail, intent, tone, lang)
    return WritingResult(result=_generate(db, context, prompt))


def translate(
    db: Session,
    context: LlmTaskContext,
    *,
    source: str,
    target_lang: str,
) -> WritingResult:
    """본문을 대상 언어로 재번역한다(편집된 한국어↔외국어 양방향 갱신용)."""
    prompt = prompts.build_translate_prompt(source, target_lang)
    return WritingResult(result=_generate(db, context, prompt))
