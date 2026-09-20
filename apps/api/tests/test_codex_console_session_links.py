from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import CompanyAppControl, DesktopSessionLink
from open_work_hub_api.domains.auth.security import hash_token


def test_codex_console_session_link_exchanges_once(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "codex_console_launch_url", "https://console.test/")
    web_session = dev_login(client)

    link = _create(client, token=web_session["token"])
    assert link["code"].startswith("cc1_")

    desktop_exchange = client.post(
        "/api/v1/auth/desktop-session-links/exchange",
        json={"code": link["code"]},
    )
    assert desktop_exchange.status_code == 401

    exchange = _exchange(client, code=link["code"])
    assert exchange == {"authenticated": True, "subject": web_session["user"]["id"]}
    assert client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": link["code"]},
    ).status_code == 401


def test_codex_console_session_link_rechecks_source_session_and_app_access(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "codex_console_launch_url", "https://console.test/")
    web_session = dev_login(client)
    link = _create(client, token=web_session["token"])

    with get_session_factory()() as db:
        db.get(CompanyAppControl, "codex-console").enabled = False
        db.commit()

    assert client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": link["code"]},
    ).status_code == 401

    with get_session_factory()() as db:
        db.get(CompanyAppControl, "codex-console").enabled = True
        db.commit()
    next_link = _create(client, token=web_session["token"])
    assert client.post(
        "/api/v1/auth/logout",
        headers=auth_headers(web_session["token"]),
    ).status_code == 204
    assert client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": next_link["code"]},
    ).status_code == 401


def test_codex_console_session_link_rejects_expired_and_desktop_codes(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "codex_console_launch_url", "https://console.test/")
    web_session = dev_login(client)
    desktop = client.post(
        "/api/v1/auth/desktop-session-links",
        headers=auth_headers(web_session["token"]),
    ).json()
    assert desktop["code"].startswith("ds1_")
    assert client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": desktop["code"]},
    ).status_code == 401

    link = _create(client, token=web_session["token"])
    with get_session_factory()() as db:
        row = db.query(DesktopSessionLink).filter_by(code_hash=hash_token(link["code"])).one()
        row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": link["code"]},
    ).status_code == 401


def _create(client: TestClient, *, token: str) -> dict:
    response = client.post(
        "/api/v1/auth/codex-console-session-links",
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _exchange(client: TestClient, *, code: str) -> dict:
    response = client.post(
        "/api/v1/auth/codex-console-session-links/exchange",
        json={"code": code},
    )
    assert response.status_code == 200, response.text
    return response.json()
