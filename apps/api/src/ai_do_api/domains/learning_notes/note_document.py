"""Pure NativeDoc mapping helpers for personal learning notes."""
from __future__ import annotations

import json
from typing import Any

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.docs.models import NativeDoc, NativeDocPage

from .schemas import MAX_CONTENT_BLOCKS_BYTES, Visibility


SOURCE_APP = "learning"
SOURCE_KIND_PUBLIC = "lesson_note_public"
SOURCE_KIND_PRIVATE = "lesson_note_private"
SOURCE_KINDS_ALL = (SOURCE_KIND_PUBLIC, SOURCE_KIND_PRIVATE)

PAGE_TITLE = "페이지 노트"


def build_source_ref(course_slug: str, lesson_id: str) -> str:
    return f"{course_slug}:{lesson_id}"


def kind_for_visibility(visibility: Visibility) -> str:
    if visibility == "public":
        return SOURCE_KIND_PUBLIC
    if visibility == "private":
        return SOURCE_KIND_PRIVATE
    raise localized_http_exception(status_code=422, code="learning.unknown_visibility")


def visibility_from_kind(kind: str) -> Visibility:
    if kind == SOURCE_KIND_PUBLIC:
        return "public"
    if kind == SOURCE_KIND_PRIVATE:
        return "private"
    # Defensive — should not happen since service queries filter by SOURCE_KINDS_ALL.
    return "private"


def validate_content_blocks(content_blocks: list[dict]) -> list[dict]:
    if not isinstance(content_blocks, list):
        raise localized_http_exception(
            status_code=422,
            code="learning.content_blocks_list_required",
        )
    for index, block in enumerate(content_blocks):
        if not isinstance(block, dict):
            raise localized_http_exception(
                status_code=422,
                code="learning.content_block_object_required",
                index=index,
            )
        if "type" not in block or not isinstance(block["type"], str):
            raise localized_http_exception(
                status_code=422,
                code="learning.content_block_type_required",
                index=index,
            )
    try:
        payload_size = len(json.dumps(content_blocks).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise localized_http_exception(
            status_code=422,
            code="learning.content_blocks_not_serializable",
        ) from exc
    if payload_size > MAX_CONTENT_BLOCKS_BYTES:
        raise localized_http_exception(
            status_code=413,
            code="learning.content_blocks_too_large",
        )
    return content_blocks


def serialize_list_item(doc: NativeDoc, *, viewer_id: str) -> dict[str, Any]:
    course_slug, lesson_id = parse_source_ref(doc.source_ref)
    return {
        "doc_id": doc.id,
        "course_slug": course_slug,
        "lesson_id": lesson_id,
        "visibility": visibility_from_kind(doc.source_kind),
        "author_id": doc.owner_id,
        "author_name": author_display_name(doc),
        "is_mine": doc.owner_id == viewer_id,
        "updated_at": doc.updated_at,
    }


def serialize_detail(
    doc: NativeDoc, page: NativeDocPage, *, viewer_id: str
) -> dict[str, Any]:
    course_slug, lesson_id = parse_source_ref(doc.source_ref)
    return {
        "doc_id": doc.id,
        "page_id": page.id,
        "course_slug": course_slug,
        "lesson_id": lesson_id,
        "visibility": visibility_from_kind(doc.source_kind),
        "author_id": doc.owner_id,
        "author_name": author_display_name(doc),
        "is_mine": doc.owner_id == viewer_id,
        "title": doc.title,
        "content_blocks": page.content_blocks or [],
        "trashed_at": doc.trashed_at,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def author_display_name(doc: NativeDoc) -> str:
    owner = getattr(doc, "owner", None)
    if owner is None:
        return ""
    return owner.display_name or owner.full_name or owner.email


def parse_source_ref(source_ref: str | None) -> tuple[str, str]:
    if not source_ref or ":" not in source_ref:
        return "", ""
    course_slug, _, lesson_id = source_ref.partition(":")
    return course_slug, lesson_id


def compose_title(*, lesson_title: str, user: User) -> str:
    author = user.display_name or user.full_name or user.email
    return f"{lesson_title.strip()} 노트 · {author}"
