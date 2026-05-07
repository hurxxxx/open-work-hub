from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.domains.docs.models import NativeDoc
from ai_do_api.domains.docs.service import create_native_doc_for_user
from ai_do_api.domains.meeting.models import Meeting


def _paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def _heading(text: str, level: int = 2) -> dict:
    return {
        "type": "heading",
        "props": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def build_minutes_blocks(summary_text: str, transcript_text: str) -> list[dict]:
    summary_lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    transcript_lines = [line.strip() for line in transcript_text.splitlines() if line.strip()]
    blocks: list[dict] = [_heading("회의 요약", level=1)]
    if summary_lines:
        blocks.extend(_paragraph(line) for line in summary_lines)
    else:
        blocks.append(_paragraph("요약을 생성하지 못했습니다."))
    blocks.append(_heading("전사 원문"))
    if transcript_lines:
        blocks.extend(_paragraph(line) for line in transcript_lines)
    else:
        blocks.append(_paragraph("전사 원문이 없습니다."))
    return blocks


def create_meeting_minutes_doc(
    db: Session,
    *,
    meeting: Meeting,
    transcript_text: str,
    summary_text: str,
    owner_id: str,
) -> NativeDoc:
    doc, _page = create_native_doc_for_user(
        db,
        workspace_id=meeting.workspace_id,
        owner_id=owner_id,
        title=f"회의록: {meeting.title} ({meeting.start_at:%Y-%m-%d})",
        first_page_title="회의록",
        content_blocks=build_minutes_blocks(summary_text, transcript_text),
        source_app="meeting",
        source_kind="app_generated",
        source_ref=meeting.id,
        generation_kind="system_ai",
    )
    return doc
