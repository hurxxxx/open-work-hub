from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ai_do_api.domains.learning_notes.note_document import (
    SOURCE_KIND_PRIVATE,
    SOURCE_KIND_PUBLIC,
    build_source_ref,
    compose_title,
    kind_for_visibility,
    parse_source_ref,
    serialize_detail,
    serialize_list_item,
    validate_content_blocks,
    visibility_from_kind,
)
from ai_do_api.domains.learning_notes.schemas import MAX_CONTENT_BLOCKS_BYTES


def _assert_http_error(
    exc_info: pytest.ExceptionInfo[HTTPException], *, status_code: int, code: str
) -> None:
    assert exc_info.value.status_code == status_code
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["X-AI-DO-Error-Code"] == code


def test_source_ref_build_and_parse() -> None:
    assert build_source_ref("course-1", "lesson-1") == "course-1:lesson-1"
    assert parse_source_ref("course-1:lesson-1") == ("course-1", "lesson-1")
    assert parse_source_ref("course-1:unit:lesson") == ("course-1", "unit:lesson")
    assert parse_source_ref(None) == ("", "")
    assert parse_source_ref("malformed") == ("", "")


def test_visibility_kind_mapping() -> None:
    assert kind_for_visibility("public") == SOURCE_KIND_PUBLIC
    assert kind_for_visibility("private") == SOURCE_KIND_PRIVATE
    assert visibility_from_kind(SOURCE_KIND_PUBLIC) == "public"
    assert visibility_from_kind(SOURCE_KIND_PRIVATE) == "private"

    # Defensive fallback preserves historical behavior for unexpected doc kinds.
    assert visibility_from_kind("unexpected") == "private"

    with pytest.raises(HTTPException) as exc_info:
        kind_for_visibility("team")
    _assert_http_error(
        exc_info,
        status_code=422,
        code="learning.unknown_visibility",
    )


def test_validate_content_blocks_accepts_existing_shape_without_copying() -> None:
    blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "note"}]}]

    assert validate_content_blocks(blocks) is blocks


@pytest.mark.parametrize(
    ("content_blocks", "status_code", "code"),
    [
        (
            {"type": "paragraph"},
            422,
            "learning.content_blocks_list_required",
        ),
        (
            ["paragraph"],
            422,
            "learning.content_block_object_required",
        ),
        (
            [{"content": []}],
            422,
            "learning.content_block_type_required",
        ),
        (
            [{"type": 123}],
            422,
            "learning.content_block_type_required",
        ),
        (
            [{"type": "paragraph", "content": object()}],
            422,
            "learning.content_blocks_not_serializable",
        ),
    ],
)
def test_validate_content_blocks_rejects_malformed_payloads(
    content_blocks: object, status_code: int, code: str
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_content_blocks(content_blocks)  # type: ignore[arg-type]

    _assert_http_error(exc_info, status_code=status_code, code=code)


def test_validate_content_blocks_rejects_oversized_payload() -> None:
    oversized_text = "x" * MAX_CONTENT_BLOCKS_BYTES

    with pytest.raises(HTTPException) as exc_info:
        validate_content_blocks([{"type": "paragraph", "text": oversized_text}])

    _assert_http_error(
        exc_info,
        status_code=413,
        code="learning.content_blocks_too_large",
    )


def test_serialize_list_item_projects_native_doc_fields() -> None:
    updated_at = datetime(2026, 5, 30, 1, 2, 3)
    doc = SimpleNamespace(
        id="doc-1",
        source_ref="course-1:lesson-1",
        source_kind=SOURCE_KIND_PUBLIC,
        owner_id="author-1",
        owner=SimpleNamespace(
            display_name="Display Name",
            full_name="Full Name",
            email="author@example.com",
        ),
        updated_at=updated_at,
    )

    assert serialize_list_item(doc, viewer_id="viewer-1") == {
        "doc_id": "doc-1",
        "course_slug": "course-1",
        "lesson_id": "lesson-1",
        "visibility": "public",
        "author_id": "author-1",
        "author_name": "Display Name",
        "is_mine": False,
        "updated_at": updated_at,
    }


def test_serialize_detail_projects_native_doc_and_page_fields() -> None:
    created_at = datetime(2026, 5, 30, 1, 2, 3)
    updated_at = datetime(2026, 5, 30, 4, 5, 6)
    doc = SimpleNamespace(
        id="doc-1",
        source_ref="course-1:lesson-1",
        source_kind=SOURCE_KIND_PRIVATE,
        owner_id="author-1",
        owner=SimpleNamespace(display_name="", full_name="Author Name", email=""),
        title="Lesson Note",
        trashed_at=None,
        created_at=created_at,
        updated_at=updated_at,
    )
    page = SimpleNamespace(id="page-1", content_blocks=None)

    assert serialize_detail(doc, page, viewer_id="author-1") == {
        "doc_id": "doc-1",
        "page_id": "page-1",
        "course_slug": "course-1",
        "lesson_id": "lesson-1",
        "visibility": "private",
        "author_id": "author-1",
        "author_name": "Author Name",
        "is_mine": True,
        "title": "Lesson Note",
        "content_blocks": [],
        "trashed_at": None,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def test_serialize_projection_falls_back_for_missing_owner() -> None:
    doc = SimpleNamespace(
        id="doc-1",
        source_ref=None,
        source_kind="unexpected",
        owner_id="author-1",
        title="Lesson Note",
        trashed_at=None,
        created_at=datetime(2026, 5, 30, 1, 2, 3),
        updated_at=datetime(2026, 5, 30, 4, 5, 6),
    )

    item = serialize_list_item(doc, viewer_id="author-1")

    assert item["course_slug"] == ""
    assert item["lesson_id"] == ""
    assert item["visibility"] == "private"
    assert item["author_name"] == ""
    assert item["is_mine"] is True


def test_compose_title_strips_lesson_title_and_uses_author_precedence() -> None:
    assert (
        compose_title(
            lesson_title="  Orientation  ",
            user=SimpleNamespace(
                display_name="Display",
                full_name="Full",
                email="user@example.com",
            ),
        )
        == "Orientation 노트 · Display"
    )
    assert (
        compose_title(
            lesson_title="Orientation",
            user=SimpleNamespace(
                display_name="",
                full_name="Full",
                email="user@example.com",
            ),
        )
        == "Orientation 노트 · Full"
    )
