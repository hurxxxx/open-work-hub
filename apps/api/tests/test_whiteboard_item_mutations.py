from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.whiteboard.access import (
    load_whiteboard_for_share_token_or_404,
    load_whiteboard_for_user_or_404,
)
from open_work_hub_api.domains.whiteboard.item_mutations import (
    WhiteboardItemUpdateCommand,
    update_whiteboard_item,
)
from dev_accounts import dev_login


def test_update_command_preserves_updated_at_for_noop_scene(client: TestClient) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    whiteboard = _create_whiteboard(client, owner["token"], title="Noop Board")

    with _bound_delivery_hub_session() as db:
        user = _load_user(db, owner["user"]["id"])
        context = load_whiteboard_for_user_or_404(db, whiteboard["id"], user)
        board = context.whiteboard
        access = context.access
        updated_at = board.updated_at

        result = update_whiteboard_item(
            db,
            WhiteboardItemUpdateCommand(
                whiteboard=board,
                access=access,
                scene={
                    "elements": [],
                    "appState": {
                        "name": "Transient editor state",
                        "selectedElementIds": {},
                        "scrollX": 32,
                    },
                    "files": {},
                    "type": "excalidraw",
                },
                update_scene=True,
            ),
        )

        assert result.changed is False
        assert result.scene_changed is False
        assert result.whiteboard.updated_at == updated_at


def test_update_command_reuses_private_item_and_shared_link_access(
    client: TestClient,
) -> None:
    owner = _dev_login(client, "delivery-hub-admin")
    recipient = _dev_login(client, "delivery-hub-member")
    whiteboard = _create_whiteboard(client, owner["token"], title="Reusable Board")
    share_token = _create_edit_link_share(client, owner["token"], whiteboard["id"])

    with _bound_delivery_hub_session() as db:
        owner_user = _load_user(db, owner["user"]["id"])
        context = load_whiteboard_for_user_or_404(db, whiteboard["id"], owner_user)
        board = context.whiteboard
        access = context.access

        private_result = update_whiteboard_item(
            db,
            WhiteboardItemUpdateCommand(
                whiteboard=board,
                access=access,
                title="Reusable Board v2",
            ),
        )

        assert private_result.changed is True
        assert private_result.whiteboard.title == "Reusable Board v2"

    shared_scene = {
        "elements": [{"id": "shared-1", "type": "text", "text": "via link"}],
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    with _bound_delivery_hub_session() as db:
        recipient_user = _load_user(db, recipient["user"]["id"])
        shared_context = load_whiteboard_for_share_token_or_404(
            db,
            share_token,
            recipient_user,
        )
        shared_board = shared_context.whiteboard
        shared_access = shared_context.access

        shared_result = update_whiteboard_item(
            db,
            WhiteboardItemUpdateCommand(
                whiteboard=shared_board,
                access=shared_access,
                scene=shared_scene,
                update_scene=True,
            ),
        )

        assert shared_result.changed is True
        assert shared_result.scene_changed is True
        assert shared_result.whiteboard.scene == shared_scene


def _bound_delivery_hub_session() -> Session:
    db = get_session_factory()()
    return db


def _load_user(db: Session, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id))
    assert user is not None
    return user


def _create_whiteboard(client: TestClient, token: str, *, title: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/whiteboard/items",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_edit_link_share(client: TestClient, token: str, item_id: str) -> str:
    response = client.put(
        f"/api/v1/whiteboard/items/{item_id}/sharing/link",
        headers=_auth_headers(token),
        json={"access_level": "edit"},
    )
    assert response.status_code == 200, response.text
    token_value = response.json()["link_share"]["token"]
    assert isinstance(token_value, str)
    return token_value


def _dev_login(client: TestClient, account_key: str) -> dict[str, Any]:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
