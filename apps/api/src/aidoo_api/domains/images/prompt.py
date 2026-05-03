"""Pure prompt-construction helpers for the image-wizard plan + agent input.

Kept side-effect free so unit tests don't need DB or LLM access.
"""

from __future__ import annotations

import re
from typing import Any

from aidoo_api.domains.images.template_catalog import describe_template_for_prompt


# --- Plan generation (OpenAI Agents SDK) -----------------------------------

_ANGLE_TOKEN_RE = re.compile(r"<\s*([^<>]{1,80})\s*>")
_DROP_PLACEHOLDER_VALUES = {
    "metric",
    "metrics",
    "status",
    "priority",
    "client",
    "label",
    "title",
    "description",
    "copy",
    "text",
    "설명 텍스트",
}


def _is_placeholder_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip()).lower()
    return normalized in _DROP_PLACEHOLDER_VALUES or normalized.startswith("placeholder")


def sanitize_image_plan_text(text: str) -> str:
    """Remove placeholder tokens before a plan is shown or sent to image generation."""

    def replace_angle_token(match: re.Match[str]) -> str:
        inner = re.sub(r"\s+", " ", match.group(1).strip())
        if not inner or _is_placeholder_value(inner):
            return ""
        return inner

    cleaned = _ANGLE_TOKEN_RE.sub(replace_angle_token, text or "")
    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        stripped = line.lstrip("-* ").strip()
        if not stripped:
            continue
        if re.match(r"^[^:：]{1,48}[:：]\s*$", stripped):
            continue
        if _is_placeholder_value(stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


BRIEF_SYSTEM_PROMPT = (
    "You are a senior image-planning agent preparing a short plan for a human "
    "reviewer and an illustrator agent. Produce plain text, at most 160 words, "
    "with the following sections in this exact order:\n\n"
    "제목: a short natural title\n"
    "목표: what the image should communicate\n"
    "구성: what the viewer will see and where\n"
    "화면에 넣을 텍스트: exact visible text to render, or '없음'\n"
    "스타일: palette, visual style, and typography direction\n"
    "확인 필요: any missing fact the human may want to supply, or '없음'\n\n"
    "Hard rules:\n"
    "- Never invent numbers, names, dates, percentages, logos, or facts.\n"
    "- Never output placeholder tokens or angle-bracket text. Forbidden "
    "examples: <metric>, <status>, <priority>, <설명 텍스트>, <클라이언트>.\n"
    "- If an exact value is missing, omit it from visible text and mention the "
    "missing fact under 확인 필요 in natural language.\n"
    "- Do NOT expose internal layout IDs, template IDs, status codes, or "
    "developer terms such as top_title_grid or status_report.\n"
    "- Do NOT include any preamble, explanation, JSON, or markdown.\n"
    "- Write in the same language the user wrote the audience/notes in; if "
    "unclear, default to Korean."
)


def _summarize_meeting(snapshot: dict[str, Any]) -> str:
    pieces: list[str] = []
    title = (snapshot.get("title") or "").strip()
    if title:
        pieces.append(f"제목: {title}")
    agenda = (snapshot.get("agenda") or snapshot.get("summary") or "").strip()
    if agenda:
        pieces.append(f"안건/요약: {agenda[:1500]}")
    actions = snapshot.get("action_items") or snapshot.get("actions") or []
    if isinstance(actions, list) and actions:
        rendered = "\n".join(
            f"- {str(item)[:200]}" for item in actions[:10] if str(item).strip()
        )
        if rendered:
            pieces.append("액션 아이템:\n" + rendered)
    return "\n".join(pieces)


def _summarize_doc(snapshot: dict[str, Any]) -> str:
    pieces: list[str] = []
    title = (snapshot.get("title") or "").strip()
    if title:
        pieces.append(f"제목: {title}")
    body = (snapshot.get("body") or snapshot.get("summary") or "").strip()
    if body:
        pieces.append(f"본문 발췌: {body[:1500]}")
    return "\n".join(pieces)


def _summarize_task(snapshot: dict[str, Any]) -> str:
    pieces: list[str] = []
    title = (snapshot.get("title") or snapshot.get("name") or "").strip()
    if title:
        pieces.append(f"제목: {title}")
    status = (snapshot.get("status") or "").strip()
    if status:
        pieces.append(f"상태: {status}")
    description = (snapshot.get("description") or snapshot.get("summary") or "").strip()
    if description:
        pieces.append(f"설명: {description[:600]}")
    issues = snapshot.get("issues") or []
    if isinstance(issues, list) and issues:
        rendered = "\n".join(
            f"- {str(item)[:200]}" for item in issues[:15] if str(item).strip()
        )
        if rendered:
            pieces.append("항목:\n" + rendered)
    return "\n".join(pieces)


_SUMMARIZERS = {
    "meeting": _summarize_meeting,
    "doc": _summarize_doc,
    "task": _summarize_task,
}


def _format_context_block(context_refs: list[dict[str, Any]]) -> str:
    if not context_refs:
        return "(첨부된 컨텍스트 없음)"
    sections: list[str] = []
    for ref in context_refs:
        kind = str(ref.get("kind") or "").lower()
        snapshot = ref.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        summarizer = _SUMMARIZERS.get(kind)
        body = summarizer(snapshot) if summarizer else ""
        if not body:
            continue
        header = {
            "meeting": "[회의록]",
            "doc": "[문서]",
            "task": "[태스크]",
        }.get(kind, f"[{kind}]")
        sections.append(f"{header}\n{body}")
    if not sections:
        return "(첨부된 컨텍스트의 본문이 비어 있음)"
    return "\n\n".join(sections)


def _format_style(style: dict[str, Any]) -> str:
    chips = style.get("chips") or []
    chips_str = ", ".join(str(c) for c in chips if str(c).strip()) if isinstance(chips, list) else ""
    palette = str(style.get("palette") or "").strip()
    background = str(style.get("background") or "").strip()
    quality = str(style.get("quality") or "").strip()
    parts = [
        f"칩: {chips_str or '(없음)'}",
        f"팔레트: {palette or '(자동)'}",
        f"배경: {background or '(자동)'}",
        f"품질: {quality or 'high'}",
    ]
    return " / ".join(parts)


def _format_layout(layout: dict[str, Any]) -> str:
    layout_id = str(layout.get("layout_id") or "").strip()
    aspect = str(layout.get("aspect") or "").strip()
    return f"레이아웃: {layout_id or '(자동)'} / 종횡비: {aspect or '1024x1024'}"


def _format_use_case(use_case: str, use_case_other: str) -> str:
    use_case = (use_case or "").strip()
    other = (use_case_other or "").strip()
    if use_case == "other" and other:
        return f"기타: {other}"
    return use_case or "(미지정)"


def build_brief_messages(
    *,
    use_case: str,
    use_case_other: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    details: dict[str, Any],
    context_refs: list[dict[str, Any]],
    reference_image_count: int,
    template_name: str | None = None,
    prior_brief: str | None = None,
    edit_instruction: str | None = None,
) -> list[dict[str, str]]:
    audience = str((details or {}).get("audience") or "").strip()
    notes = str((details or {}).get("notes") or "").strip()
    blocks: list[str] = []
    template_summary = describe_template_for_prompt(template_name)
    if template_summary:
        blocks.append(f"[Template]\n{template_summary}")
    blocks.extend(
        [
            f"사용처: {_format_use_case(use_case, use_case_other)}",
            _format_style(style or {}),
            _format_layout(layout or {}),
            f"청중/톤: {audience or '(미지정)'}",
            f"기타 메모: {notes or '(없음)'}",
            f"참고 이미지 수: {reference_image_count}장",
            "",
            "[컨텍스트]",
            _format_context_block(context_refs or []),
        ]
    )
    user_message = "\n".join(blocks)

    if prior_brief and edit_instruction:
        user_message += (
            "\n\n[이전 계획]\n"
            + prior_brief.strip()
            + "\n\n[수정 요청]\n"
            + edit_instruction.strip()
            + "\n\n위 수정 요청을 반영해서 동일한 형식으로 전체 계획을 다시 출력하세요."
        )
    elif edit_instruction:
        user_message += (
            "\n\n[수정 요청]\n"
            + edit_instruction.strip()
            + "\n\n위 수정 요청을 반영해서 계획을 출력하세요."
        )

    return [
        {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


def build_direct_edit_prompt(*, edit_instruction: str, style: dict[str, Any]) -> str:
    """Build the internal prompt used when an image edit skips human plan review."""

    instruction = sanitize_image_plan_text(edit_instruction)
    style_summary = _format_style(style or {})
    if not instruction:
        return ""
    return (
        "수정 요청: "
        f"{instruction}\n"
        "기준 이미지: 첨부된 composition 참고 이미지를 이전 결과물로 보고, 사용자가 "
        "요청하지 않은 구도, 주요 내용, 텍스트, 브랜드 느낌은 가능한 유지하세요.\n"
        "스타일: 기존 이미지의 시각 톤을 유지하되 아래 스타일 메타와 충돌하지 않게 "
        f"반영하세요. {style_summary}\n"
        "화면 텍스트: 원본의 텍스트를 유지하고, 사용자가 명시적으로 요청한 텍스트 변경만 "
        "적용하세요.\n"
        "주의: 숫자, 이름, 날짜, 로고, 사실관계는 임의로 새로 만들지 마세요."
    )


# --- Image generation (OpenAI Agents SDK) ----------------------------------

ILLUSTRATOR_SYSTEM_PROMPT = (
    "You are an infographic illustrator agent. The user has approved an image "
    "plan and (optionally) supplied reference images with explicit roles "
    "('style', 'composition', or 'content'). You must call the image_generation "
    "tool to produce the final image. Honor the approved plan's goal, "
    "composition, visible text, style, and cautions. Reference images are "
    "guidance only - do not copy them literally unless their role is "
    "'composition'. If a template sample reference image is present, use it for "
    "layout, polish, hierarchy, and visual style only; do not copy its filler "
    "text, numbers, logos, or sample facts. Never render placeholder tokens, "
    "angle-bracket labels, or "
    "raw template words for metrics, statuses, priorities, description text, "
    "or internal template IDs. If a value is missing, omit the text or use "
    "unlabeled visual structure. Output exactly one image. Do not write "
    "commentary."
)


def build_agent_prompt(
    *,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_roles: list[str],
) -> str:
    """Build the text portion of the agent input, excluding image attachments."""

    plan_text = sanitize_image_plan_text(brief_text)
    style_summary = _format_style(style or {})
    layout_summary = _format_layout(layout or {})
    has_template_sample = any("template" in role.lower() for role in reference_roles)
    refs = (
        ", ".join(reference_roles)
        if reference_roles
        else "(참고 이미지 없음)"
    )
    template_sample_note = (
        "\n[템플릿 샘플 이미지]\n"
        "참고 이미지 역할 순서에 template composition이 있으면 그 이미지는 선택된 템플릿의 "
        "고품질 샘플입니다. 구도, 위계, 완성도, 스타일만 참고하고 샘플 안의 임시 문구, "
        "숫자, 로고, 사실관계는 복사하지 마세요.\n\n"
        if has_template_sample
        else ""
    )
    body = (
        "[승인된 이미지 계획]\n"
        f"{plan_text}\n\n"
        "[스타일 메타]\n"
        f"{style_summary}\n\n"
        "[레이아웃 메타]\n"
        f"{layout_summary}\n\n"
        f"[참고 이미지 역할 순서] {refs}\n\n"
        f"{template_sample_note}"
        "[금지 규칙]\n"
        "꺾쇠괄호로 감싼 텍스트, 누락값 표기, 내부 템플릿 ID/코드명, "
        "임시 라벨은 이미지 안에 렌더링하지 마세요.\n\n"
        "위 계획을 충실히 반영해 한 장의 이미지를 생성하세요. "
        "계획에 명시되지 않은 숫자/이름/로고는 임의로 추가하지 마세요. "
        "금지 텍스트와 꺾쇠괄호 텍스트는 이미지 안에 절대 렌더링하지 마세요. "
        "최종 결과는 이미지 한 장만 반환하고 추가 설명 텍스트는 출력하지 마세요."
    )
    return body
