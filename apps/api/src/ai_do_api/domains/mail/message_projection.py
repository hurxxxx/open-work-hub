from __future__ import annotations

from collections.abc import Iterable

from ai_do_api.domains.mail.models import MailMessage
from ai_do_api.domains.mail.schemas import (
    MailMessageDetail,
    MailMessageListResponse,
    MailMessageSummary,
)


def build_message_list_response(
    rows: Iterable[MailMessage],
    *,
    total: int,
) -> MailMessageListResponse:
    return MailMessageListResponse(
        items=[MailMessageSummary.model_validate(row) for row in rows],
        total=total,
    )


def build_message_detail(row: MailMessage) -> MailMessageDetail:
    body = row.body
    return MailMessageDetail(
        **MailMessageSummary.model_validate(row).model_dump(),
        body={
            "text_body": body.text_body if body is not None else "",
            "html_body": body.html_body if body is not None else "",
        },
        attachments=[attachment for attachment in row.attachments],
    )


def message_text(row: MailMessage) -> str:
    body = row.body
    if body is None:
        return row.snippet
    return body.text_body or body.html_body or row.snippet


def mail_prompt_context(
    row: MailMessage,
    body_text: str,
    *,
    max_body_chars: int = 20000,
) -> str:
    return (
        f"Subject: {row.subject}\n"
        f"From: {row.from_text}\n"
        f"To: {row.to_text}\n"
        f"Date: {row.received_at or ''}\n\n"
        f"{body_text[:max_body_chars]}"
    )


def reply_subject(subject: str) -> str:
    stripped = subject.strip()
    if stripped.lower().startswith("re:"):
        return stripped
    return f"Re: {stripped}" if stripped else "Re:"
