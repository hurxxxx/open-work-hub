from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_alm_api.domains.docs import access_context


def test_native_doc_and_page_refs_normalize_raw_and_prefixed_ids() -> None:
    assert access_context.normalize_doc_id("doc-1") == "doc-1"
    assert access_context.normalize_doc_id("native_doc__doc-1") == "doc-1"
    assert access_context.normalize_page_id("page-1") == "page-1"
    assert access_context.normalize_page_id("native_doc_page__page-1") == "page-1"


def test_native_ref_normalization_rejects_wrong_prefix_with_not_found_code() -> None:
    with pytest.raises(HTTPException) as doc_error:
        access_context.normalize_doc_id("native_doc_page__page-1")
    with pytest.raises(HTTPException) as page_error:
        access_context.normalize_page_id("native_doc__doc-1")

    assert doc_error.value.status_code == 404
    assert doc_error.value.detail.code == "docs.doc_not_found"
    assert page_error.value.status_code == 404
    assert page_error.value.detail.code == "docs.page_not_found"


def test_share_token_workspace_bypass_only_allows_native_refs() -> None:
    assert access_context.share_token_allows_item_without_docs_access("doc-1") is True
    assert access_context.share_token_allows_item_without_docs_access("native_doc__doc-1") is True
    assert access_context.share_token_allows_item_without_docs_access("file__doc-1") is False
    assert access_context.share_token_allows_page_without_docs_access("page-1") is True
    assert (
        access_context.share_token_allows_page_without_docs_access("native_doc_page__page-1")
        is True
    )
    assert access_context.share_token_allows_page_without_docs_access("native_doc__page-1") is False


def test_missing_docs_workspace_context_raises_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(access_context, "get_current_workspace", lambda _db: None)
    monkeypatch.setattr(access_context, "resolve_workspaces", lambda _db, _user: [])

    with pytest.raises(HTTPException) as exc_info:
        access_context.ensure_docs_workspace_access(object(), SimpleNamespace(id="user-1"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail.code == "docs.requests_workspace_context_required"
