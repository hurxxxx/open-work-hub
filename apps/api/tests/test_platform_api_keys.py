from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.admin.api_keys_router import router as api_keys_router
from open_alm_api.domains.auth.models import AuditLog, PlatformApiKey
from open_alm_api.domains.auth.platform_api_keys import (
    PlatformApiPrincipal,
    PlatformApiKeyServiceError,
    hash_platform_api_key,
    require_platform_api_scope,
    revoke_platform_api_key,
)
from dev_accounts import auth_headers, dev_login


pytestmark = pytest.mark.fresh_api_app


def _register_test_routes(client: TestClient) -> None:
    if not any(
        getattr(route, "path", None) == "/api/v1/admin/api-keys" for route in client.app.routes
    ):
        client.app.include_router(api_keys_router, prefix="/api/v1")

    if any(
        getattr(route, "path", None) == "/api/v1/platform-api-key-probe"
        for route in client.app.routes
    ):
        return

    @client.app.get("/api/v1/platform-api-key-probe")
    def platform_api_key_probe(
        principal: PlatformApiPrincipal = Depends(require_platform_api_scope("hr:read")),
    ) -> dict[str, object]:
        return {
            "key_id": principal.key_id,
            "scopes": sorted(principal.scopes),
        }


def test_admin_platform_api_key_lifecycle_matches_ui_contract(
    client: TestClient,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    admin_headers = auth_headers(admin_session["token"])

    issued_response = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={
            "name": "HR integration",
            "scopes": ["hr:read", "hr:read"],
        },
    )
    assert issued_response.status_code == 201, issued_response.text
    assert issued_response.headers["cache-control"] == "private, no-store"
    assert issued_response.headers["pragma"] == "no-cache"
    issued = issued_response.json()
    secret = issued["api_key"]
    item = issued["item"]
    assert secret.startswith("aido_pk_")
    assert set(item) == {
        "id",
        "name",
        "key_prefix",
        "scopes",
        "created_by_name",
        "created_at",
        "last_used_at",
        "revoked_at",
    }
    assert item["name"] == "HR integration"
    assert item["key_prefix"] == secret[:18]
    assert item["scopes"] == ["hr:read"]
    assert item["created_by_name"] != "-"
    assert item["last_used_at"] is None
    assert item["revoked_at"] is None
    assert "token_hash" not in issued_response.text
    assert "secret_ciphertext" not in issued_response.text

    with get_session_factory()() as db:
        row = db.get(PlatformApiKey, item["id"])
        assert row is not None
        assert row.token_hash == hash_platform_api_key(secret)
        assert row.token_hash != secret
        assert secret not in row.secret_ciphertext

    listed_response = client.get(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
    )
    assert listed_response.status_code == 200, listed_response.text
    assert listed_response.headers["cache-control"] == "private, no-store"
    assert listed_response.headers["pragma"] == "no-cache"
    listed = listed_response.json()
    assert listed["available_scopes"] == ["hr:read"]
    assert listed["items"] == [item]
    assert secret not in listed_response.text
    assert "api_key" not in listed_response.text

    revealed_response = client.post(
        f"/api/v1/admin/api-keys/{item['id']}/reveal",
        headers=admin_headers,
    )
    assert revealed_response.status_code == 200, revealed_response.text
    assert revealed_response.headers["cache-control"] == "private, no-store"
    assert revealed_response.headers["pragma"] == "no-cache"
    assert revealed_response.json() == {
        "item": item,
        "api_key": secret,
    }

    session_probe = client.get(
        "/api/v1/platform-api-key-probe",
        headers=admin_headers,
    )
    assert session_probe.status_code == 401
    assert session_probe.headers["x-open-alm-error-code"] == "platform_api_key.invalid"
    assert session_probe.headers["cache-control"] == "private, no-store"
    assert session_probe.headers["pragma"] == "no-cache"

    key_probe = client.get(
        "/api/v1/platform-api-key-probe",
        headers=auth_headers(secret),
    )
    assert key_probe.status_code == 200, key_probe.text
    assert key_probe.json() == {
        "key_id": item["id"],
        "scopes": ["hr:read"],
    }

    with get_session_factory()() as db:
        used_row = db.get(PlatformApiKey, item["id"])
        assert used_row is not None and used_row.last_used_at is not None

    revoked_response = client.post(
        f"/api/v1/admin/api-keys/{item['id']}/revoke",
        headers=admin_headers,
    )
    assert revoked_response.status_code == 200, revoked_response.text
    assert revoked_response.headers["cache-control"] == "private, no-store"
    assert revoked_response.headers["pragma"] == "no-cache"
    revoked = revoked_response.json()
    assert set(revoked) == set(item)
    assert revoked["revoked_at"] is not None

    with get_session_factory()() as db:
        revoked_row = db.get(PlatformApiKey, item["id"])
        assert revoked_row is not None
        assert revoked_row.secret_ciphertext == ""

    rejected_probe = client.get(
        "/api/v1/platform-api-key-probe",
        headers=auth_headers(secret),
    )
    assert rejected_probe.status_code == 401
    assert rejected_probe.headers["x-open-alm-error-code"] == "platform_api_key.invalid"
    assert rejected_probe.headers["cache-control"] == "private, no-store"
    assert rejected_probe.headers["pragma"] == "no-cache"

    rejected_reveal = client.post(
        f"/api/v1/admin/api-keys/{item['id']}/reveal",
        headers=admin_headers,
    )
    assert rejected_reveal.status_code == 409
    assert rejected_reveal.headers["x-open-alm-error-code"] == "admin.platform_api_key_inactive"
    rejected_revoke = client.post(
        f"/api/v1/admin/api-keys/{item['id']}/revoke",
        headers=admin_headers,
    )
    assert rejected_revoke.status_code == 409
    assert rejected_revoke.headers["x-open-alm-error-code"] == "admin.platform_api_key_inactive"

    with get_session_factory()() as db:
        audits = list(
            db.scalars(select(AuditLog).where(AuditLog.entity_kind == "platform_api_key")).all()
        )
        actions = {audit.action for audit in audits}
        assert {
            "admin.platform_api_key.issue",
            "admin.platform_api_key.list",
            "admin.platform_api_key.reveal",
            "admin.platform_api_key.revoke",
        }.issubset(actions)
        audit_text = json.dumps(
            [
                {
                    "summary": audit.summary,
                    "payload": audit.payload,
                }
                for audit in audits
            ],
            ensure_ascii=False,
        )
        assert secret not in audit_text
        assert "HR integration" not in audit_text


def test_admin_platform_api_keys_reject_unknown_scopes_and_non_admins(
    client: TestClient,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    admin_headers = auth_headers(admin_session["token"])

    invalid_scope = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={"name": "Invalid scope", "scopes": ["hr:write"]},
    )
    assert invalid_scope.status_code == 400
    assert invalid_scope.headers["x-open-alm-error-code"] == "admin.platform_api_key_scope_invalid"

    for deceptive_name in ("line\nbreak", "trusted\u202ereversed"):
        invalid_name = client.post(
            "/api/v1/admin/api-keys",
            headers=admin_headers,
            json={"name": deceptive_name, "scopes": ["hr:read"]},
        )
        assert invalid_name.status_code == 400
        assert invalid_name.headers["x-open-alm-error-code"] == "admin.platform_api_key_name_invalid"

    issued = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={"name": "Permission boundary", "scopes": ["hr:read"]},
    ).json()
    key_id = issued["item"]["id"]

    member_session = dev_login(client, "delivery-hub-member")
    member_headers = auth_headers(member_session["token"])
    forbidden_requests = (
        client.get("/api/v1/admin/api-keys", headers=member_headers),
        client.post(
            "/api/v1/admin/api-keys",
            headers=member_headers,
            json={"name": "Forbidden", "scopes": ["hr:read"]},
        ),
        client.post(
            f"/api/v1/admin/api-keys/{key_id}/reveal",
            headers=member_headers,
        ),
        client.post(
            f"/api/v1/admin/api-keys/{key_id}/revoke",
            headers=member_headers,
        ),
    )
    assert all(response.status_code == 403 for response in forbidden_requests)

    missing = client.get("/api/v1/admin/api-keys")
    assert missing.status_code == 401


def test_platform_api_key_rejects_malformed_tokens_and_cannot_become_a_user_session(
    client: TestClient,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    admin_headers = auth_headers(admin_session["token"])
    issued = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={"name": "Boundary checks", "scopes": ["hr:read"]},
    ).json()
    secret = issued["api_key"]

    malformed_tokens = (
        "aido_pk_",
        f"aido_pk_{'A' * 42}",
        f"aido_pk_{'A' * 44}",
        f"aido_pk_{'!' * 43}",
        f"aido_pk_{'A' * 10_000}",
        f"aido_pk_{'Z' * 43}",
    )
    for malformed in malformed_tokens:
        rejected = client.get(
            "/api/v1/platform-api-key-probe",
            headers=auth_headers(malformed),
        )
        assert rejected.status_code == 401
        assert rejected.headers["x-open-alm-error-code"] == "platform_api_key.invalid"
        assert rejected.headers["cache-control"] == "private, no-store"
        assert rejected.headers["pragma"] == "no-cache"

    query_only = client.get(
        "/api/v1/platform-api-key-probe",
        params={"api_key": secret},
    )
    assert query_only.status_code == 401
    assert query_only.headers["x-open-alm-error-code"] == "platform_api_key.required"
    assert query_only.headers["cache-control"] == "private, no-store"
    assert query_only.headers["pragma"] == "no-cache"

    assert client.get("/api/v1/auth/me", headers=auth_headers(secret)).status_code == 401
    assert client.get("/api/v1/admin/api-keys", headers=auth_headers(secret)).status_code == 401
    assert (
        client.get(
            "/api/v1/platform-api-key-probe",
            headers=auth_headers(secret),
        ).status_code
        == 200
    )


def test_platform_api_key_encryption_root_fails_closed_without_breaking_hash_auth(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    admin_headers = auth_headers(admin_session["token"])
    issued = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={"name": "Rotation check", "scopes": ["hr:read"]},
    ).json()
    key_id = issued["item"]["id"]
    secret = issued["api_key"]

    monkeypatch.setenv(
        "OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
        "rotated-platform-key-test-root",
    )
    get_settings.cache_clear()
    try:
        failed_reveal = client.post(
            f"/api/v1/admin/api-keys/{key_id}/reveal",
            headers=admin_headers,
        )
        assert failed_reveal.status_code == 503
        assert (
            failed_reveal.headers["x-open-alm-error-code"]
            == "admin.platform_api_key_encryption_unavailable"
        )

        authenticated = client.get(
            "/api/v1/platform-api-key-probe",
            headers=auth_headers(secret),
        )
        assert authenticated.status_code == 200

        revoked = client.post(
            f"/api/v1/admin/api-keys/{key_id}/revoke",
            headers=admin_headers,
        )
        assert revoked.status_code == 200
    finally:
        get_settings.cache_clear()


def test_platform_api_key_issue_requires_an_encryption_root(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    monkeypatch.setenv("OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/v1/admin/api-keys",
            headers=auth_headers(admin_session["token"]),
            json={"name": "Must fail", "scopes": ["hr:read"]},
        )
        assert response.status_code == 503
        assert (
            response.headers["x-open-alm-error-code"]
            == "admin.platform_api_key_encryption_unavailable"
        )
        with get_session_factory()() as db:
            assert db.scalar(select(PlatformApiKey.id)) is None
    finally:
        get_settings.cache_clear()


def test_platform_api_key_admin_openapi_never_accepts_platform_key_auth(
    client: TestClient,
) -> None:
    _register_test_routes(client)
    client.app.openapi_schema = None
    schema = client.app.openapi()
    operations = [
        schema["paths"][path]["get" if path == "/api/v1/admin/api-keys" else "post"]
        for path in (
            "/api/v1/admin/api-keys",
            "/api/v1/admin/api-keys/{key_id}/reveal",
            "/api/v1/admin/api-keys/{key_id}/revoke",
        )
    ]

    assert all(operation.get("security") != [{"PlatformApiKey": []}] for operation in operations)
    reveal_operation = operations[1]
    assert "requestBody" not in reveal_operation
    serialized_schema = json.dumps(schema, ensure_ascii=False)
    assert '"token_hash"' not in serialized_schema
    assert '"secret_ciphertext"' not in serialized_schema


def test_concurrent_platform_api_key_revocation_has_one_winner(
    client: TestClient,
) -> None:
    _register_test_routes(client)
    admin_session = dev_login(client)
    admin_headers = auth_headers(admin_session["token"])
    issued = client.post(
        "/api/v1/admin/api-keys",
        headers=admin_headers,
        json={"name": "Concurrent revocation", "scopes": ["hr:read"]},
    ).json()
    key_id = issued["item"]["id"]
    actor_user_id = admin_session["user"]["id"]
    barrier = Barrier(2)

    def attempt_revoke() -> str:
        with get_session_factory()() as db:
            barrier.wait(timeout=5)
            try:
                revoke_platform_api_key(
                    db,
                    key_id=key_id,
                    actor_user_id=actor_user_id,
                )
                db.commit()
            except PlatformApiKeyServiceError as error:
                db.rollback()
                return error.code
        return "revoked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: attempt_revoke(), range(2)))

    assert outcomes == ["admin.platform_api_key_inactive", "revoked"]
    with get_session_factory()() as db:
        row = db.get(PlatformApiKey, key_id)
        assert row is not None
        assert row.status == "revoked"
        assert row.secret_ciphertext == ""
