"""Tests for the personal learning notes endpoints.

Covers the permission matrix from ``plans/06-learning-annotations.md``:
  * anonymous -> 401 on every endpoint
  * any authenticated user can upsert their own note with public/private toggle
  * the list endpoint never leaks other users' private notes
  * detail/archive/restore of another user's note -> 404 (hide existence)
  * platform admin has NO special privilege over private notes
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AI-DO Admin",
            "email": "admin@ai-do.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_member(
    client: TestClient, admin_token: str, *, email: str, full_name: str = "Member"
) -> tuple[str, str]:
    """Create a non-admin user and return (user_id, token)."""
    password = "memberpw12345"
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={
            "email": email,
            "full_name": full_name,
            "temporary_password": password,
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return user_id, login.json()["token"]


_COURSE = "vibe-coding-foundations"
_LESSON = "vcf-001-orientation"
_BLOCKS = [
    {"type": "paragraph", "content": [{"type": "text", "text": "개인 메모."}]}
]


def _payload(visibility: str = "private", text: str = "개인 메모.") -> dict:
    return {
        "course_slug": _COURSE,
        "lesson_id": _LESSON,
        "lesson_title": "오리엔테이션",
        "visibility": visibility,
        "content_blocks": [
            {"type": "paragraph", "content": [{"type": "text", "text": text}]}
        ],
    }


def test_anonymous_requests_are_rejected(client: TestClient) -> None:
    _bootstrap_admin_session(client)
    assert client.get(
        "/api/v1/learning/notes",
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    ).status_code == 401
    assert client.get(
        "/api/v1/learning/notes/me",
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    ).status_code == 401
    assert client.put("/api/v1/learning/notes/me", json=_payload()).status_code == 401
    assert client.get("/api/v1/learning/notes/anything").status_code == 401
    assert client.post("/api/v1/learning/notes/anything/archive").status_code == 401
    assert client.post("/api/v1/learning/notes/anything/restore").status_code == 401


def test_any_user_can_create_and_edit_their_own_private_note(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")

    response = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="private", text="alice 사설 노트"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visibility"] == "private"
    assert body["is_mine"] is True
    assert body["author_name"]  # populated from display_name/full_name/email
    doc_id = body["doc_id"]

    # Re-upsert updates the same document and can flip visibility.
    updated = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="public", text="alice 공개 노트"),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["doc_id"] == doc_id
    assert updated.json()["visibility"] == "public"

    # GET /me returns my note directly.
    mine = client.get(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert mine.status_code == 200
    assert mine.json()["doc_id"] == doc_id


def test_private_notes_are_hidden_from_everyone_else_including_admin(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")
    _, bob_token = _create_member(client, admin["token"], email="bob@ai-do.local")

    created = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="private", text="alice 사설"),
    )
    assert created.status_code == 200
    alice_doc_id = created.json()["doc_id"]

    # Bob's list excludes Alice's private note.
    bob_list = client.get(
        "/api/v1/learning/notes",
        headers=_auth_headers(bob_token),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert bob_list.status_code == 200
    assert bob_list.json()["items"] == []

    # Bob cannot fetch the detail either — 404, not 403.
    bob_detail = client.get(
        f"/api/v1/learning/notes/{alice_doc_id}",
        headers=_auth_headers(bob_token),
    )
    assert bob_detail.status_code == 404

    # Platform admin has no special privilege over private notes.
    admin_detail = client.get(
        f"/api/v1/learning/notes/{alice_doc_id}",
        headers=_auth_headers(admin["token"]),
    )
    assert admin_detail.status_code == 404

    admin_list = client.get(
        "/api/v1/learning/notes",
        headers=_auth_headers(admin["token"]),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert admin_list.status_code == 200
    assert admin_list.json()["items"] == []


def test_public_notes_are_listed_and_readable_by_everyone(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    alice_id, alice_token = _create_member(
        client, admin["token"], email="alice@ai-do.local", full_name="Alice"
    )
    _, bob_token = _create_member(
        client, admin["token"], email="bob@ai-do.local", full_name="Bob"
    )

    alice_note = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="public", text="alice 공개 노트"),
    )
    assert alice_note.status_code == 200
    alice_doc_id = alice_note.json()["doc_id"]

    # Bob sees Alice's public note in the list with is_mine=False.
    bob_list = client.get(
        "/api/v1/learning/notes",
        headers=_auth_headers(bob_token),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert bob_list.status_code == 200
    items = bob_list.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["doc_id"] == alice_doc_id
    assert item["visibility"] == "public"
    assert item["author_id"] == alice_id
    assert item["author_name"] == "Alice"
    assert item["is_mine"] is False

    # Bob fetches detail.
    bob_detail = client.get(
        f"/api/v1/learning/notes/{alice_doc_id}",
        headers=_auth_headers(bob_token),
    )
    assert bob_detail.status_code == 200
    assert bob_detail.json()["content_blocks"][0]["content"][0]["text"] == "alice 공개 노트"


def test_list_returns_own_private_note_at_top_alongside_others_public(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")
    _, bob_token = _create_member(client, admin["token"], email="bob@ai-do.local")

    # Bob creates a public note first.
    client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(bob_token),
        json=_payload(visibility="public", text="bob 공개"),
    )
    # Alice creates a private note after.
    client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="private", text="alice 사설"),
    )

    list_response = client.get(
        "/api/v1/learning/notes",
        headers=_auth_headers(alice_token),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 2
    # Own note first, then public from others.
    assert items[0]["is_mine"] is True
    assert items[0]["visibility"] == "private"
    assert items[1]["is_mine"] is False
    assert items[1]["visibility"] == "public"


def test_archive_and_restore_are_owner_only(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")
    _, bob_token = _create_member(client, admin["token"], email="bob@ai-do.local")

    created = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="public", text="alice 공개"),
    )
    alice_doc_id = created.json()["doc_id"]

    # Bob cannot archive Alice's note.
    assert (
        client.post(
            f"/api/v1/learning/notes/{alice_doc_id}/archive",
            headers=_auth_headers(bob_token),
        ).status_code
        == 404
    )
    # Neither can admin.
    assert (
        client.post(
            f"/api/v1/learning/notes/{alice_doc_id}/archive",
            headers=_auth_headers(admin["token"]),
        ).status_code
        == 404
    )

    # Alice archives her own.
    archived = client.post(
        f"/api/v1/learning/notes/{alice_doc_id}/archive",
        headers=_auth_headers(alice_token),
    )
    assert archived.status_code == 200
    assert archived.json()["trashed_at"] is not None

    # After archive, it disappears from the list.
    listed = client.get(
        "/api/v1/learning/notes",
        headers=_auth_headers(alice_token),
        params={"course_slug": _COURSE, "lesson_id": _LESSON},
    )
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    # Alice restores.
    restored = client.post(
        f"/api/v1/learning/notes/{alice_doc_id}/restore",
        headers=_auth_headers(alice_token),
    )
    assert restored.status_code == 200
    assert restored.json()["trashed_at"] is None


def test_upsert_rejects_malformed_content_blocks(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")

    bad = _payload()
    bad["content_blocks"] = [{"no_type_field": True}]
    response = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=bad,
    )
    assert response.status_code == 422


def test_upsert_rejects_invalid_visibility(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")

    bad = _payload()
    bad["visibility"] = "world"
    response = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=bad,
    )
    assert response.status_code == 422


def test_native_doc_tagging(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    _, alice_token = _create_member(client, admin["token"], email="alice@ai-do.local")

    response = client.put(
        "/api/v1/learning/notes/me",
        headers=_auth_headers(alice_token),
        json=_payload(visibility="public"),
    )
    assert response.status_code == 200
    doc_id = response.json()["doc_id"]

    from sqlalchemy import select

    from ai_do_api.core.db import get_session_factory
    from ai_do_api.domains.docs.models import NativeDoc

    factory = get_session_factory()
    with factory() as session:
        doc = session.scalar(select(NativeDoc).where(NativeDoc.id == doc_id))
        assert doc is not None
        assert doc.source_app == "learning"
        assert doc.source_kind == "lesson_note_public"
        assert doc.source_ref == f"{_COURSE}:{_LESSON}"
