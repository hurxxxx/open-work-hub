from __future__ import annotations

from typing import Any, Callable


def summarize_meeting_context(snapshot: dict[str, Any]) -> str:
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


def summarize_doc_context(snapshot: dict[str, Any]) -> str:
    pieces: list[str] = []
    title = (snapshot.get("title") or "").strip()
    if title:
        pieces.append(f"제목: {title}")
    body = (snapshot.get("body") or snapshot.get("summary") or "").strip()
    if body:
        pieces.append(f"본문 발췌: {body[:1500]}")
    return "\n".join(pieces)


def summarize_task_context(snapshot: dict[str, Any]) -> str:
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


ContextSummarizer = Callable[[dict[str, Any]], str]

CONTEXT_SUMMARIZERS: dict[str, ContextSummarizer] = {
    "meeting": summarize_meeting_context,
    "doc": summarize_doc_context,
    "task": summarize_task_context,
}


def format_image_context_block(context_refs: list[dict[str, Any]]) -> str:
    if not context_refs:
        return "(첨부된 컨텍스트 없음)"
    sections: list[str] = []
    for ref in context_refs:
        kind = str(ref.get("kind") or "").lower()
        snapshot = ref.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            snapshot = {}
        summarizer = CONTEXT_SUMMARIZERS.get(kind)
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
