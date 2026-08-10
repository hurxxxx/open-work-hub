from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from ai_do_api.domains.realtime import docs_pages_subscription
from ai_do_api.domains.realtime.docs_pages_subscription import (
    resolve_docs_pages_subscription,
    resolve_docs_pages_subscription_in_session,
)


class _FakeDb:
    def __init__(self, user: object | None = None) -> None:
        self.user = user
        self.closed = False

    def get(self, _model: object, _id: str) -> object | None:
        return self.user

    def close(self) -> None:
        self.closed = True


def _install_auth(monkeypatch: pytest.MonkeyPatch, *, auth_user_id: str = "user-1") -> None:
    monkeypatch.setattr(
        docs_pages_subscription,
        "resolve_auth_context_from_token",
        lambda _db, _token, update_last_seen: SimpleNamespace(
            user=SimpleNamespace(id=auth_user_id),
        ),
    )


def test_docs_pages_subscription_rejects_invalid_payload_key() -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_docs_pages_subscription({}, token="token", user_id="user-1")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail.code == "validation.value_invalid"


def test_docs_pages_subscription_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDb(user=SimpleNamespace(id="user-1"))
    _install_auth(monkeypatch)
    monkeypatch.setattr(docs_pages_subscription, "get_session_factory", lambda: lambda: db)
    monkeypatch.setattr(
        docs_pages_subscription,
        "_share_token_allows_item_without_docs_access",
        lambda _item_id: True,
    )
    monkeypatch.setattr(
        docs_pages_subscription,
        "_native_doc_from_item_or_404",
        lambda _db, _item_id, _user, *, share_token: (
            SimpleNamespace(id="doc-1", updated_at=datetime(2026, 1, 1, 12, 0)),
            SimpleNamespace(can_view=True),
        ),
    )

    result = resolve_docs_pages_subscription(
        {"key": "doc-1", "share_token": "share"},
        token="token",
        user_id="user-1",
    )

    assert result.doc_id == "doc-1"
    assert result.updated_at == datetime(2026, 1, 1, 12, 0)
    assert db.closed is True


def test_docs_pages_subscription_denies_workspace_without_member_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(user=SimpleNamespace(id="user-1"))
    workspace = SimpleNamespace(id="workspace-1", key="hq")
    _install_auth(monkeypatch)
    monkeypatch.setattr(
        docs_pages_subscription,
        "_share_token_allows_item_without_docs_access",
        lambda _item_id: False,
    )
    monkeypatch.setattr(
        docs_pages_subscription,
        "load_active_workspace_by_key",
        lambda _db, _slug: workspace,
    )
    monkeypatch.setattr(docs_pages_subscription, "bind_current_workspace", lambda *_args: None)
    monkeypatch.setattr(
        docs_pages_subscription,
        "resolve_workspace_role",
        lambda _db, _user, _workspace_id: None,
    )
    monkeypatch.setattr(
        docs_pages_subscription,
        "workspace_role_allows",
        lambda _role, _min_role: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        resolve_docs_pages_subscription_in_session(
            db,
            item_id="doc-1",
            workspace_slug="hq",
            share_token=None,
            token="token",
            user_id="user-1",
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail.code == "workspace.membership_required"


def test_docs_pages_subscription_returns_doc_snapshot_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(user=SimpleNamespace(id="user-1"))
    updated_at = datetime(2026, 2, 3, 4, 5)
    _install_auth(monkeypatch)
    monkeypatch.setattr(
        docs_pages_subscription,
        "_share_token_allows_item_without_docs_access",
        lambda _item_id: False,
    )
    monkeypatch.setattr(
        docs_pages_subscription,
        "_ensure_docs_workspace_access",
        lambda _db, _user: SimpleNamespace(id="workspace-1"),
    )
    monkeypatch.setattr(
        docs_pages_subscription,
        "_native_doc_from_item_or_404",
        lambda _db, _item_id, _user, *, share_token: (
            SimpleNamespace(id="doc-1", updated_at=updated_at),
            SimpleNamespace(can_view=True),
        ),
    )

    result = resolve_docs_pages_subscription_in_session(
        db,
        item_id="doc-1",
        workspace_slug=None,
        share_token=None,
        token="token",
        user_id="user-1",
    )

    assert result.doc_id == "doc-1"
    assert result.updated_at == updated_at
