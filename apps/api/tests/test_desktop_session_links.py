from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import auth_headers, dev_login


def test_desktop_session_link_exchanges_once(client: TestClient) -> None:
    web_session = dev_login(client)

    link = _create_desktop_session_link(client, token=web_session["token"])
    assert link["code"]
    assert "expires_at" in link

    desktop_session = _exchange_desktop_session_link(client, code=link["code"])
    assert desktop_session["token"] != web_session["token"]
    assert desktop_session["user"]["id"] == web_session["user"]["id"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers=auth_headers(desktop_session["token"]),
    )
    assert me_response.status_code == 200, me_response.text

    second_exchange_response = client.post(
        "/api/v1/auth/desktop-session-links/exchange",
        json={"code": link["code"]},
    )
    assert second_exchange_response.status_code == 401


def test_desktop_session_link_rejects_after_source_logout(client: TestClient) -> None:
    web_session = dev_login(client)
    link = _create_desktop_session_link(client, token=web_session["token"])

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(web_session["token"]),
    )
    assert logout_response.status_code == 204, logout_response.text

    exchange_response = client.post(
        "/api/v1/auth/desktop-session-links/exchange",
        json={"code": link["code"]},
    )
    assert exchange_response.status_code == 401


def _create_desktop_session_link(client: TestClient, *, token: str) -> dict:
    response = client.post(
        "/api/v1/auth/desktop-session-links",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _exchange_desktop_session_link(client: TestClient, *, code: str) -> dict:
    response = client.post(
        "/api/v1/auth/desktop-session-links/exchange",
        json={"code": code},
    )
    assert response.status_code == 200, response.text
    return response.json()
