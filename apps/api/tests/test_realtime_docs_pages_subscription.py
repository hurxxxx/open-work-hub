from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.realtime import docs_pages_subscription as subscriptions


class _FakeDb:
    closed = False

    def close(self):
        self.closed = True


def _auth(monkeypatch, user_id="user-1"):
    monkeypatch.setattr(
        subscriptions,
        "resolve_auth_context_from_token",
        lambda _db, _token, update_last_seen: SimpleNamespace(user=SimpleNamespace(id=user_id)),
    )


def test_docs_pages_subscription_rejects_invalid_payload_key():
    with pytest.raises(HTTPException) as denied:
        subscriptions.resolve_docs_pages_subscription({}, token="token", user_id="user-1")
    assert denied.value.status_code == 400


def test_docs_pages_subscription_closes_session_and_passes_share_context(monkeypatch):
    db = _FakeDb()
    _auth(monkeypatch)
    monkeypatch.setattr(subscriptions, "get_session_factory", lambda: lambda: db)
    calls = []
    monkeypatch.setattr(
        subscriptions,
        "_ensure_docs_app_access",
        lambda _db, user: calls.append(("admission", user.id)),
    )

    def load(_db, item_id, user, *, share_token):
        calls.append(("source", item_id, user.id, share_token))
        return SimpleNamespace(id="doc-1", updated_at=datetime(2026, 1, 1)), SimpleNamespace(
            can_view=True
        )

    monkeypatch.setattr(subscriptions, "_native_doc_from_item_or_404", load)
    result = subscriptions.resolve_docs_pages_subscription(
        {"key": "doc-1", "share_token": "share"}, token="token", user_id="user-1"
    )
    assert calls == [("admission", "user-1"), ("source", "doc-1", "user-1", "share")]
    assert result.doc_id == "doc-1"
    assert result.updated_at == datetime(2026, 1, 1)
    assert db.closed


def test_docs_pages_subscription_denies_revoked_admission_before_source_lookup(monkeypatch):
    _auth(monkeypatch)

    def deny(_db, _user):
        raise HTTPException(status_code=403)

    monkeypatch.setattr(subscriptions, "_ensure_docs_app_access", deny)
    monkeypatch.setattr(
        subscriptions,
        "_native_doc_from_item_or_404",
        lambda *_args, **_kwargs: pytest.fail("source lookup preceded app admission"),
    )
    with pytest.raises(HTTPException) as denied:
        subscriptions.resolve_docs_pages_subscription_in_session(
            _FakeDb(), item_id="doc-1", share_token="valid-link", token="token", user_id="user-1"
        )
    assert denied.value.status_code == 403


def test_docs_pages_subscription_rejects_mismatched_connection_user(monkeypatch):
    _auth(monkeypatch, "another-user")
    monkeypatch.setattr(
        subscriptions,
        "_ensure_docs_app_access",
        lambda *_args: pytest.fail("mismatched principal reached admission"),
    )
    with pytest.raises(HTTPException) as denied:
        subscriptions.resolve_docs_pages_subscription_in_session(
            _FakeDb(), item_id="doc-1", share_token=None, token="token", user_id="user-1"
        )
    assert denied.value.status_code == 401


def test_docs_pages_subscription_closes_session_on_source_denial(monkeypatch):
    db = _FakeDb()
    _auth(monkeypatch)
    monkeypatch.setattr(subscriptions, "get_session_factory", lambda: lambda: db)
    monkeypatch.setattr(subscriptions, "_ensure_docs_app_access", lambda *_args: None)
    monkeypatch.setattr(
        subscriptions,
        "_native_doc_from_item_or_404",
        lambda *_args, **_kwargs: (SimpleNamespace(id="doc-1"), SimpleNamespace(can_view=False)),
    )
    with pytest.raises(HTTPException) as denied:
        subscriptions.resolve_docs_pages_subscription(
            {"key": "doc-1"}, token="token", user_id="user-1"
        )
    assert denied.value.status_code == 403
    assert db.closed


@pytest.mark.parametrize("share_token", [False, 123, {}, [], ""])
def test_docs_subscription_rejects_malformed_link_instead_of_using_direct_acl(share_token):
    with pytest.raises(HTTPException) as denied:
        subscriptions.resolve_docs_pages_subscription(
            {"key": "doc-1", "share_token": share_token}, token="token", user_id="user-1"
        )
    assert denied.value.status_code == 400
