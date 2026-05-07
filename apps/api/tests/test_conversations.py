from __future__ import annotations

from fastapi.testclient import TestClient

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _login,
)


def _workspace_slug(client: TestClient, token: str) -> str:
    response = client.get("/api/v1/admin/workspaces", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    workspace = response.json()[0]
    return workspace.get("slug", workspace["key"])


def _create(client: TestClient, token: str, slug: str, title: str = "") -> dict:
    response = client.post(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_then_list_returns_own_conversation(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="스프린트 계획")
    assert created["id"]
    assert created["title"] == "스프린트 계획"
    assert created["turns"] == []

    listing = client.get(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(token),
    )
    assert listing.status_code == 200
    body = listing.json()
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert body["nextCursor"] is None


def test_get_returns_detail_with_turns_ordered(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="test")

    # Append turns directly via the service layer to avoid coupling this
    # test to a chat stream integration that doesn't exist yet.
    from ai_do_api.core.db import get_engine
    from ai_do_api.domains.conversations import service
    from ai_do_api.domains.conversations.models import Conversation
    from sqlalchemy.orm import Session

    with Session(get_engine()) as db:
        conversation = db.get(Conversation, created["id"])
        assert conversation is not None
        service.append_turn(db, conversation=conversation, role="user", content="hi")
        service.append_turn(
            db,
            conversation=conversation,
            role="assistant",
            content="hello!",
            meta={
                "policy": "local_only",
                "chosen_pool": "local",
                "reasoning": "thinking about greeting",
                "pii_hits": ["email"],
                "tool_calls": [{"call_id": "c1", "name": "search"}],
                "unknown_extra_field": "dropped silently",
            },
        )

    response = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert [turn["role"] for turn in body["turns"]] == ["user", "assistant"]
    assert [turn["seq"] for turn in body["turns"]] == [0, 1]

    # Meta is flattened into top-level camelCase fields matching the
    # frontend ChatTurn contract — not left as an opaque `meta` blob.
    assistant_turn = body["turns"][1]
    assert assistant_turn["policy"] == "local_only"
    assert assistant_turn["chosenPool"] == "local"
    assert assistant_turn["reasoning"] == "thinking about greeting"
    assert assistant_turn["piiHits"] == ["email"]
    assert assistant_turn["toolCalls"] == [{"call_id": "c1", "name": "search"}]
    assert "meta" not in assistant_turn
    assert "unknown_extra_field" not in assistant_turn


def test_patch_renames_conversation(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="initial")
    response = client.patch(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "updated"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "updated"


def test_patch_empty_title_rejected(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="x")
    response = client.patch(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "   "},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "conversations.title_empty"


def test_legacy_create_rejects_unsupported_scope(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    response = client.post(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "docs_page",
            "scopeResourceId": "doc-1",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "conversations.unsupported_scope"
    assert response.json()["params"]["scope_ref"] == "docs_page"


def test_legacy_create_rejects_incomplete_scope_pair(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    response = client.post(
        f"/api/v1/workspaces/{slug}/conversations",
        headers={**_auth_headers(token), "Accept-Language": "ko-KR"},
        json={
            "title": "",
            "scopeRef": "meeting",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "conversations.scope_pair_required"
    assert response.json()["detail"] == "scope_ref와 scope_resource_id는 함께 제공해야 합니다."


def test_legacy_create_rejects_meeting_scope_for_non_participant(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    admin_token = session["token"]
    slug = _workspace_slug(client, admin_token)
    meeting = _create_meeting(client, admin_token, title="Private scope meeting")
    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="conversation-outsider@ai-do.local",
        full_name="Conversation Outsider",
        workspace_keys=[slug],
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    response = client.post(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(outsider_token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )

    assert response.status_code == 403


def test_delete_soft_hides_from_list_but_direct_get_also_404s(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="gone")
    response = client.delete(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    assert response.status_code == 204

    listing = client.get(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(token),
    )
    assert listing.status_code == 200
    assert created["id"] not in [item["id"] for item in listing.json()["items"]]

    # Soft-delete is not the same as hard-delete, but we still refuse to
    # serve a deleted conversation to the user — preserving rows purely so
    # an admin could restore them out-of-band.
    direct = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    assert direct.status_code == 404


def test_list_respects_pagination_cursor(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    ids = [_create(client, token, slug, title=f"c{i}")["id"] for i in range(5)]

    first_page = client.get(
        f"/api/v1/workspaces/{slug}/conversations?limit=2",
        headers=_auth_headers(token),
    ).json()
    assert len(first_page["items"]) == 2
    assert first_page["nextCursor"] is not None

    second_page = client.get(
        f"/api/v1/workspaces/{slug}/conversations?limit=2"
        f"&cursor={first_page['nextCursor']}",
        headers=_auth_headers(token),
    ).json()
    assert len(second_page["items"]) == 2

    seen = {item["id"] for item in first_page["items"]}
    seen |= {item["id"] for item in second_page["items"]}
    # The five ids we created should be fully covered after one more page.
    third_page = client.get(
        f"/api/v1/workspaces/{slug}/conversations?limit=2"
        f"&cursor={second_page['nextCursor']}",
        headers=_auth_headers(token),
    ).json()
    seen |= {item["id"] for item in third_page["items"]}
    assert set(ids) <= seen


def test_pagination_cursor_is_stable_on_ties(client: TestClient) -> None:
    # Regression for a pagination bug where a timestamp-only cursor could
    # silently drop rows that shared the same updated_at as the page
    # boundary. All conversations created in the same tick must still be
    # reachable across pages.
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    from datetime import datetime, timezone

    from ai_do_api.core.db import get_engine
    from ai_do_api.domains.conversations.models import Conversation
    from sqlalchemy.orm import Session

    created_ids: list[str] = []
    for i in range(6):
        created_ids.append(_create(client, token, slug, title=f"tied-{i}")["id"])

    # Force every conversation to share the exact same updated_at so any
    # cursor that ignores the id component drops rows.
    shared = datetime.now(timezone.utc).replace(tzinfo=None)
    with Session(get_engine()) as db:
        rows = (
            db.query(Conversation)
            .filter(Conversation.id.in_(created_ids))
            .all()
        )
        for row in rows:
            row.updated_at = shared
        db.commit()

    page_size = 2
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(4):
        url = f"/api/v1/workspaces/{slug}/conversations?limit={page_size}"
        if cursor:
            url += f"&cursor={cursor}"
        body = client.get(url, headers=_auth_headers(token)).json()
        seen |= {item["id"] for item in body["items"]}
        cursor = body["nextCursor"]
        if cursor is None:
            break

    assert set(created_ids) <= seen, (
        "Pagination dropped rows on timestamp tie. "
        f"Missing: {set(created_ids) - seen}"
    )


def test_append_turn_unique_seq_prevents_duplicates(client: TestClient) -> None:
    # Regression for a race where two transactions both computed the same
    # `len(conversation.turns)` before either commit landed, silently
    # inserting duplicate seq values. The unique constraint now forces the
    # second writer into IntegrityError; append_turn retries and lands at
    # seq+1 instead of colliding.
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="race")

    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session

    from ai_do_api.core.db import get_engine
    from ai_do_api.domains.conversations import service
    from ai_do_api.domains.conversations.models import (
        Conversation,
        ConversationTurn,
    )

    # Simulate a concurrent append having already landed by inserting a turn
    # with seq=0 directly; a second append must detect the collision and
    # land at seq=1 rather than retrying forever or writing another seq=0.
    with Session(get_engine()) as db:
        conversation = db.get(Conversation, created["id"])
        assert conversation is not None
        existing = ConversationTurn(
            id="fixed-existing-0",
            conversation_id=conversation.id,
            seq=0,
            role="user",
            content="pre-existing",
            meta=None,
        )
        db.add(existing)
        db.commit()

        # Ensure the unique constraint is actually in place for this feature
        # so future refactors can't silently drop it.
        duplicate = ConversationTurn(
            id="would-collide",
            conversation_id=conversation.id,
            seq=0,
            role="user",
            content="collides",
            meta=None,
        )
        db.add(duplicate)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:  # pragma: no cover - constraint should always trigger
            raise AssertionError(
                "Expected UNIQUE (conversation_id, seq) to reject the duplicate"
            )

        service.append_turn(
            db,
            conversation=conversation,
            role="assistant",
            content="second",
        )

    response = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    seqs = [turn["seq"] for turn in response.json()["turns"]]
    assert seqs == [0, 1], f"Expected seq to skip the collision, got {seqs}"


def test_get_requires_ownership(client: TestClient) -> None:
    # A bogus id should 404, not leak 200 or 403 — enforces the "scoped to
    # owner" contract.
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    response = client.get(
        f"/api/v1/workspaces/{slug}/conversations/does-not-exist",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "conversations.not_found"
