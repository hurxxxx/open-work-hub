from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.qna.constants import (
    QNA_KIND_NOTICE,
    QNA_NOTICE_CATEGORY,
    QNA_SCOPE_KIND,
)
from ai_do_api.domains.qna.models import QnaDocument
from ai_do_api.domains.qna import service
from ai_do_api.domains.rag.models import RagSyncJob
from ai_do_api.domains.retrieval.models import (
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from dev_accounts import auth_headers, dev_login


def test_qna_document_detail_returns_body_text_without_bloating_lists(
    client: TestClient,
) -> None:
    session = dev_login(client)
    body_text = "공지 본문입니다.\n첨부 파일 추출 내용입니다."
    with get_session_factory()() as db:
        db.add(
            QnaDocument(
                id="qna-detail-doc",
                scope_kind=QNA_SCOPE_KIND,
                workspace_id=None,
                kind=QNA_KIND_NOTICE,
                external_id="notice-001",
                title="복지 공지",
                category=QNA_NOTICE_CATEGORY,
                author="관리팀",
                posted_at="2026-06-24",
                body_text=body_text,
                attachments=["guide.pdf"],
                char_count=len(body_text),
                content_checksum="checksum",
                rag_status="indexed",
                chunk_count=2,
            )
        )
        db.commit()

    list_response = client.get(
        "/api/v1/qna/notices",
        headers=auth_headers(session["token"]),
    )
    assert list_response.status_code == 200, list_response.text
    notice = list_response.json()["notices"][0]
    assert notice["id"] == "qna-detail-doc"
    assert "body_text" not in notice

    detail_response = client.get(
        "/api/v1/qna/documents/qna-detail-doc",
        headers=auth_headers(session["token"]),
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["title"] == "복지 공지"
    assert detail["body_text"] == body_text


def test_upsert_notice_preserves_target_board_category(client: TestClient) -> None:
    del client
    with get_session_factory()() as db:
        doc, changed = service.upsert_notice(
            db,
            num="notice-1887",
            title="복지제도 기준",
            author="유용욱",
            posted_at="2026-04-13 10:31:02",
            body="복지제도 기준 본문",
            attachments=[],
            category=QNA_NOTICE_CATEGORY,
        )

        assert changed is True
        assert doc.category == "주요공지사항(관리팀)"


def test_unchanged_legacy_notice_heals_binding_and_delete_keeps_projection_snapshot(
    client: TestClient,
) -> None:
    del client
    title = "Legacy notice"
    body = "Already indexed content"
    checksum = service._notice_content_checksum(
        title=title,
        category=QNA_NOTICE_CATEGORY,
        body_text=body,
        attachment_names=[],
        attachment_content_hashes=None,
    )
    with get_session_factory()() as db:
        db.add(
            QnaDocument(
                id="qna-legacy-projection-fence",
                scope_kind=QNA_SCOPE_KIND,
                workspace_id=None,
                retrieval_partition_id=None,
                kind=QNA_KIND_NOTICE,
                external_id="notice-projection-fence",
                title=title,
                category=QNA_NOTICE_CATEGORY,
                body_text=body,
                attachments=[],
                char_count=len(body),
                content_checksum=checksum,
                rag_status="indexed",
            )
        )
        db.flush()

        doc, changed = service.upsert_notice(
            db,
            num="notice-projection-fence",
            title=title,
            author=None,
            posted_at=None,
            body=body,
            attachments=[],
            category=QNA_NOTICE_CATEGORY,
        )

        assert changed is False
        assert doc.retrieval_partition_id is not None
        partition_id = doc.retrieval_partition_id
        head = db.get(
            RetrievalProjectionHead,
            ("qna_document", "qna-legacy-projection-fence"),
        )
        assert head is not None
        assert head.projection_version == 1
        assert head.desired_state == "active"
        assert head.retrieval_partition_id == partition_id

        assert service.delete_document(
            db,
            document_id="qna-legacy-projection-fence",
        )
        assert db.get(QnaDocument, "qna-legacy-projection-fence") is None
        events = list(
            db.scalars(
                select(RetrievalProjectionEvent)
                .where(
                    RetrievalProjectionEvent.resource_type == "qna_document",
                    RetrievalProjectionEvent.resource_id == "qna-legacy-projection-fence",
                )
                .order_by(RetrievalProjectionEvent.projection_version)
            )
        )
        assert [event.desired_state for event in events] == ["active", "deleted"]
        assert events[-1].retrieval_partition_id == partition_id

        job = db.scalar(
            select(RagSyncJob).where(
                RagSyncJob.resource_type == "qna_document",
                RagSyncJob.resource_id == "qna-legacy-projection-fence",
                RagSyncJob.status == "pending",
            )
        )
        assert job is not None
        assert job.projection_event_sequence == events[-1].event_sequence
        assert job.projection_version == 2
        assert job.retrieval_partition_id == partition_id
        assert job.desired_state == "deleted"
        assert job.operation == "delete"
