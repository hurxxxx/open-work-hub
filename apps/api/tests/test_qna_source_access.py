from __future__ import annotations

from types import SimpleNamespace

from ai_do_api.domains.qna import source_access


def test_qna_source_access_fails_closed_when_platform_app_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr(source_access, "is_platform_app_enabled", lambda db, app_id: False)
    policy = SimpleNamespace(db=object())
    adapter = source_access.QnaDocumentSourceAccessAdapter()

    assert not adapter.can_read_resource(
        policy,
        resource_type="qna_document",
        resource_id="qna-1",
    )
    assert not adapter.can_read_rag_resource(
        policy,
        resource_type="qna_document",
        resource_id="qna-1",
    )
    assert (
        adapter.authorize_many_rag_resources(
            policy,
            resource_type="qna_document",
            resource_ids=("qna-1", "qna-2"),
        )
        == set()
    )
    assert not adapter.has_accessible_source(policy, resource_type="qna_document")
