from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from open_work_hub_api.domains.content_access import grants
from open_work_hub_api.domains.content_access.grants import (
    CONTENT_GRANT_MAX_TTL_SECONDS,
    ContentGrantIssuer,
    InvalidContentGrant,
    build_content_grant_url,
    decode_content_grant,
    require_matching_issuer,
)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(api_prefix="/api/v1", content_grant_signing_key="grant-secret")


def _url(monkeypatch, **overrides: object) -> str:
    monkeypatch.setattr(grants, "get_settings", _settings)
    values = {
        "resource_kind": "pms.attachment",
        "resource_id": "attachment-1",
        "owner_app_id": "pms",
        "issuer": ContentGrantIssuer(user_id="user-1", session_id="session-1"),
        "execution_context_kind": "company",
        "route_id": None,
        "source_type": "pms_task",
        "source_id": "task-1",
        "object_identity": "object-hash",
        "resource_version": "1",
        "disposition": "attachment",
        "expires_seconds": 60,
        "now": 100,
    }
    values.update(overrides)
    return build_content_grant_url(**values)


def _token(url: str) -> str:
    return parse_qs(urlparse(url).fragment)["grant"][0]


def test_round_trip_uses_static_path_and_canonical_claims(monkeypatch) -> None:
    url = _url(monkeypatch)
    claims = decode_content_grant(_token(url), now=100)

    assert urlparse(url).path == "/api/v1/content"
    assert not urlparse(url).query
    assert claims.issued_at == 100
    assert claims.expires == 160
    assert claims.execution_context_kind == "company"
    assert not hasattr(claims, "execution_workspace_id")


@pytest.mark.parametrize("suffix", ["A", "=", ".extra"])
def test_tampered_or_noncanonical_grants_fail_closed(monkeypatch, suffix: str) -> None:
    token = _token(_url(monkeypatch))
    with pytest.raises(InvalidContentGrant):
        decode_content_grant(token + suffix, now=100)


def test_expired_grant_and_excessive_ttl_fail_closed(monkeypatch) -> None:
    token = _token(_url(monkeypatch, expires_seconds=1))
    with pytest.raises(InvalidContentGrant, match="expired"):
        decode_content_grant(token, now=102)
    with pytest.raises(ValueError, match="TTL"):
        _url(monkeypatch, expires_seconds=CONTENT_GRANT_MAX_TTL_SECONDS + 1)


def test_context_and_route_owner_invariants_are_enforced(monkeypatch) -> None:
    with pytest.raises(ValueError, match="execution context"):
        _url(monkeypatch, execution_context_kind="workspace")
    with pytest.raises(ValueError, match="does not belong"):
        _url(monkeypatch, route_id="docs.root")
    claims = decode_content_grant(
        _token(_url(monkeypatch, execution_context_kind="personal")), now=100
    )
    assert claims.execution_context_kind == "personal"


def test_grant_is_bound_to_exact_authenticated_user_and_session(monkeypatch) -> None:
    claims = decode_content_grant(_token(_url(monkeypatch)), now=100)

    require_matching_issuer(
        claims,
        current_user_id="user-1",
        current_session_id="session-1",
    )
    with pytest.raises(InvalidContentGrant, match="issuer"):
        require_matching_issuer(
            claims,
            current_user_id="user-2",
            current_session_id="session-1",
        )
    with pytest.raises(InvalidContentGrant, match="issuer"):
        require_matching_issuer(
            claims,
            current_user_id="user-1",
            current_session_id="session-2",
        )


def test_content_grants_use_dedicated_signing_key_and_reject_rotated_key(monkeypatch) -> None:
    token = _token(_url(monkeypatch))
    monkeypatch.setattr(
        grants,
        "get_settings",
        lambda: SimpleNamespace(
            api_prefix="/api/v1",
            content_grant_signing_key="grant-secret",
            minio_secret_key="unrelated-storage-secret",
        ),
    )
    assert decode_content_grant(token, now=100).resource_id == "attachment-1"
    monkeypatch.setattr(
        grants,
        "get_settings",
        lambda: SimpleNamespace(
            api_prefix="/api/v1",
            content_grant_signing_key="rotated-grant-secret",
            minio_secret_key="grant-secret",
        ),
    )
    with pytest.raises(InvalidContentGrant):
        decode_content_grant(token, now=100)
