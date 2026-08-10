from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient
import pytest

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_user_with_workspaces,
    _first_workspace_slug,
    _login,
)


@pytest.fixture(autouse=True)
def _clear_livekit_public_url(monkeypatch: pytest.MonkeyPatch):
    from open_work_hub_api.core.settings import get_settings

    monkeypatch.setenv("OPEN_WORK_HUB_LIVEKIT_PUBLIC_URL", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _decode_jwt_payload(token: str) -> dict:
    parts = token.split(".")
    assert len(parts) == 3
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))


def _create_video_session(client: TestClient, token: str, workspace_slug: str, title: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_video_chat_session_create_list_and_join_token(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])

    session = _create_video_session(
        client,
        admin["token"],
        workspace_slug,
        "LiveKit validation",
    )

    assert session["title"] == "LiveKit validation"
    assert session["status"] == "open"
    assert session["provider"] == "livekit"
    assert session["meeting_id"] is None
    assert session["room_name"].startswith(f"open-work-hub-{workspace_slug}-")

    listed = client.get(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions",
        headers=_auth_headers(admin["token"]),
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [session["id"]]

    token_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
        headers=_auth_headers(admin["token"]),
    )
    assert token_response.status_code == 200, token_response.text
    body = token_response.json()
    claims = _decode_jwt_payload(body["token"])
    assert body["livekit_url"] == "ws://127.0.0.1:7880"
    assert claims["iss"] == "devkey"
    assert body["identity"] == claims["sub"]
    assert claims["sub"].startswith(f"{session['workspace_id']}:{admin['user']['id']}:")
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["room"] == session["room_name"]
    assert claims["video"]["canPublish"] is True
    assert claims["video"]["canSubscribe"] is True


def test_video_chat_join_token_uses_remote_request_host_for_dev_livekit_url(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    session = _create_video_session(client, admin["token"], workspace_slug, "Remote browser")

    token_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
        headers={**_auth_headers(admin["token"]), "Host": "100.87.48.58:4200"},
    )

    assert token_response.status_code == 200, token_response.text
    assert token_response.json()["livekit_url"] == "ws://100.87.48.58:7880"


def test_video_chat_join_token_prefers_configured_public_livekit_url(
    client: TestClient,
    monkeypatch,
) -> None:
    from open_work_hub_api.core.settings import get_settings

    monkeypatch.setenv("OPEN_WORK_HUB_LIVEKIT_PUBLIC_URL", "wss://video.example.test")
    get_settings.cache_clear()
    try:
        admin = _bootstrap_admin_session(client)
        workspace_slug = _first_workspace_slug(client, admin["token"])
        session = _create_video_session(client, admin["token"], workspace_slug, "Public URL")

        token_response = client.post(
            f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
            headers={**_auth_headers(admin["token"]), "Host": "100.87.48.58:4200"},
        )

        assert token_response.status_code == 200, token_response.text
        assert token_response.json()["livekit_url"] == "wss://video.example.test"
    finally:
        get_settings.cache_clear()


def test_video_chat_join_token_identity_is_unique_per_join_request(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    session = _create_video_session(client, admin["token"], workspace_slug, "Identity")

    first_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
        headers=_auth_headers(admin["token"]),
    )
    second_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
        headers=_auth_headers(admin["token"]),
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    first_claims = _decode_jwt_payload(first_response.json()["token"])
    second_claims = _decode_jwt_payload(second_response.json()["token"])
    identity_prefix = f"{session['workspace_id']}:{admin['user']['id']}:"
    assert first_claims["sub"].startswith(identity_prefix)
    assert second_claims["sub"].startswith(identity_prefix)
    assert first_claims["sub"] != second_claims["sub"]


def test_video_chat_ended_session_cannot_issue_join_token(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    session = _create_video_session(client, admin["token"], workspace_slug, "Close me")

    end_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/end",
        headers=_auth_headers(admin["token"]),
    )
    assert end_response.status_code == 200, end_response.text
    assert end_response.json()["status"] == "ended"

    token_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/join-token",
        headers=_auth_headers(admin["token"]),
    )
    assert token_response.status_code == 409, token_response.text
    assert token_response.headers["X-Open-Work-Hub-Error-Code"] == "video_chat.session_closed"


def test_video_chat_non_owner_cannot_end_session(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    session = _create_video_session(client, admin["token"], workspace_slug, "Owner only")
    member = _create_user_with_workspaces(
        client,
        admin["token"],
        email="video-member@open-work-hub.local",
        full_name="Video Member",
        workspace_keys=[workspace_slug],
    )
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    end_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/end",
        headers=_auth_headers(member_token),
    )

    assert end_response.status_code == 403, end_response.text
    assert end_response.headers["X-Open-Work-Hub-Error-Code"] == "video_chat.host_required"

    fresh_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert fresh_response.status_code == 200, fresh_response.text
    assert fresh_response.json()["status"] == "open"


def test_video_chat_recording_and_captions_are_feature_flagged(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    session = _create_video_session(client, admin["token"], workspace_slug, "Feature flags")

    recording = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/recording/start",
        headers=_auth_headers(admin["token"]),
    )
    assert recording.status_code == 503, recording.text
    assert recording.headers["X-Open-Work-Hub-Error-Code"] == "video_chat.recording_not_enabled"

    captions = client.post(
        f"/api/v1/workspaces/{workspace_slug}/video-chat/sessions/{session['id']}/captions/start",
        headers=_auth_headers(admin["token"]),
    )
    assert captions.status_code == 503, captions.text
    assert captions.headers["X-Open-Work-Hub-Error-Code"] == "video_chat.captions_not_enabled"
