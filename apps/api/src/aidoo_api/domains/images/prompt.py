"""Pure prompt-construction helpers for the image-wizard brief + agent input.

Kept side-effect free so unit tests don't need DB or LLM access.
"""

from __future__ import annotations

from typing import Any


# --- Brief generation (chat LLM) -------------------------------------------

BRIEF_SYSTEM_PROMPT = (
    "You are a senior infographic designer preparing a brief for an "
    "illustrator. Produce a tightly structured brief in plain text, at most "
    "300 words, with the following sections (each on its own line, in this "
    "order):\n\n"
    "TITLE: <short title>\n"
    "LAYOUT: <how the image is laid out>\n"
    "KEY ELEMENTS: <bullet list of concrete elements, each line starting with '- '>\n"
    "COLORS: <palette description tied to the requested style>\n"
    "TYPOGRAPHY: <typeface vibe and emphasis>\n"
    "NOTES: <anything the illustrator should avoid or be careful about>\n\n"
    "Hard rules:\n"
    "- Do NOT invent numbers, names, dates, percentages, or facts. Only use "
    "what appears in the provided context. If the user did not provide a "
    "number, write a placeholder like <metric>, never make one up.\n"
    "- Do NOT include any preamble, explanation, JSON, or markdown — only the "
    "six sections above.\n"
    "- Keep KEY ELEMENTS to at most 7 bullets.\n"
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
    prior_brief: str | None = None,
    edit_instruction: str | None = None,
) -> list[dict[str, str]]:
    audience = str((details or {}).get("audience") or "").strip()
    notes = str((details or {}).get("notes") or "").strip()
    blocks: list[str] = [
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
    user_message = "\n".join(blocks)

    if prior_brief and edit_instruction:
        user_message += (
            "\n\n[이전 브리프]\n"
            + prior_brief.strip()
            + "\n\n[수정 요청]\n"
            + edit_instruction.strip()
            + "\n\n위 수정 요청을 반영해서 동일한 형식으로 전체 브리프를 다시 출력하세요."
        )
    elif edit_instruction:
        user_message += (
            "\n\n[수정 요청]\n"
            + edit_instruction.strip()
            + "\n\n위 수정 요청을 반영해서 브리프를 출력하세요."
        )

    return [
        {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]


# --- Image generation (Codex/Agents SDK) -----------------------------------

ILLUSTRATOR_SYSTEM_PROMPT = (
    "You are an infographic illustrator agent. The user has approved an image "
    "brief and (optionally) supplied reference images with explicit roles "
    "('style', 'composition', or 'content'). You must call the image_generation "
    "tool to produce the final image. Honor the brief's TITLE/LAYOUT/KEY "
    "ELEMENTS/COLORS/TYPOGRAPHY/NOTES sections precisely. Reference images are "
    "guidance only — do not copy them literally unless their role is "
    "'composition'. Output exactly one image. Do not write commentary."
)


def build_agent_prompt(
    *,
    brief_text: str,
    style: dict[str, Any],
    layout: dict[str, Any],
    reference_roles: list[str],
) -> str:
    """Build the text portion of the agent input, excluding image attachments."""

    style_summary = _format_style(style or {})
    layout_summary = _format_layout(layout or {})
    refs = (
        ", ".join(reference_roles)
        if reference_roles
        else "(참고 이미지 없음)"
    )
    body = (
        "[승인된 브리프]\n"
        f"{brief_text.strip()}\n\n"
        "[스타일 메타]\n"
        f"{style_summary}\n\n"
        "[레이아웃 메타]\n"
        f"{layout_summary}\n\n"
        f"[참고 이미지 역할 순서] {refs}\n\n"
        "위 브리프를 충실히 반영해 한 장의 이미지를 생성하세요. "
        "브리프에 명시되지 않은 숫자/이름/로고는 임의로 추가하지 마세요. "
        "최종 결과는 이미지 한 장만 반환하고 추가 설명 텍스트는 출력하지 마세요."
    )
    return body
