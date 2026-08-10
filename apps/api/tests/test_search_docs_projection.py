from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import Team, User, Workspace
from open_alm_api.domains.docs.models import (
    DocMeetingAccess,
    DocsCollection,
    NativeDoc,
    NativeDocTarget,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.pms.models import Folder, TaskList
from open_alm_api.domains.retrieval.models import RetrievalPartition
from open_alm_api.domains.search.docs_projection import load_docs_search_document
from open_alm_api.domains.search.projections import load_search_document
from open_alm_api.domains.search.schemas import SearchEntityType


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            Team.__table__,
            Folder.__table__,
            TaskList.__table__,
            RetrievalPartition.__table__,
            DocsCollection.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocTarget.__table__,
            NativeDocUserShare.__table__,
            NativeDocLinkShare.__table__,
            Meeting.__table__,
            DocMeetingAccess.__table__,
        ],
    )
    return Session(engine)


def _add_workspace_user(session: Session, *, workspace_active: bool = True) -> None:
    session.add(
        Workspace(
            id="ws-1",
            key="delivery-hub",
            name="Delivery Hub",
            description="",
            active=workspace_active,
        )
    )
    session.add(
        User(
            id="user-1",
            login_id="docs-owner",
            email="docs-owner@open-alm.local",
            full_name="Docs Owner",
            password_hash="hash",
            status="active",
        )
    )


def _add_native_doc(session: Session, *, trashed_at: datetime | None = None) -> None:
    created_at = datetime(2026, 1, 2, 3, 4, tzinfo=UTC).replace(tzinfo=None)
    session.add(
        NativeDoc(
            id="doc-1",
            workspace_id="ws-1",
            owner_id="user-1",
            title="Budget Review",
            source_app="docs",
            source_kind="manual",
            source_ref="source-1",
            created_at=created_at,
            updated_at=created_at,
            trashed_at=trashed_at,
        )
    )
    session.add(
        NativeDocPage(
            id="page-2",
            doc_id="doc-1",
            parent_id=None,
            title="Second Page",
            content_format="block",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "later content"}]}
            ],
            sort_order=2,
            created_by_id="user-1",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.add(
        NativeDocPage(
            id="page-1",
            doc_id="doc-1",
            parent_id=None,
            title="First Page",
            content_format="block",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "budget risk"}]}
            ],
            sort_order=1,
            created_by_id="user-1",
            created_at=created_at,
            updated_at=created_at,
        )
    )
    session.add(
        NativeDocTarget(
            id="target-1",
            doc_id="doc-1",
            target_app="pms",
            target_type="space",
            target_id="team-1",
            is_primary=True,
        )
    )
    session.add(
        NativeDocUserShare(
            id="share-1",
            doc_id="doc-1",
            user_id="user-1",
            access_level="read",
            created_by_id="user-1",
        )
    )


def test_docs_search_projection_preserves_document_shape_through_dispatcher() -> None:
    session = _session()
    try:
        _add_workspace_user(session)
        _add_native_doc(session)
        session.commit()

        direct = load_docs_search_document(session, "doc-1")
        dispatched = load_search_document(
            session, entity_type=SearchEntityType.DOC, entity_id="doc-1"
        )

        assert direct is not None
        assert dispatched is not None
        assert dispatched["workspace_id"] == "ws-1"
        assert dispatched["entity_type"] == "doc"
        assert dispatched["entity_id"] == "doc-1"
        assert dispatched["title"] == "Budget Review"
        assert dispatched["summary"] == "First Page budget risk Second Page later content"
        assert dispatched["body"] == "First Page\nbudget risk\nSecond Page\nlater content"
        assert dispatched["keywords"] == "manual docs Docs Owner"
        assert dispatched["visibility"] == "shared"
        assert dispatched["owner_user_id"] == "user-1"
        assert dispatched["team_ids"] == ["team-1"]
        assert dispatched["targets"] == [
            {
                "app": "pms",
                "type": "space",
                "id": "team-1",
                "label": "pms:space:team-1",
            }
        ]
        assert dispatched["target_keys"] == ["pms:space:team-1", "space:team-1"]
        assert dispatched["shared_user_ids"] == ["user-1"]
        assert dispatched["deep_link"] == "/w/delivery-hub/docs/doc-1?page=page-1"
        assert dispatched["metadata"] == {"source_kind": "manual", "source_ref": "source-1"}
        assert dispatched["doc_pages"] == [
            {"id": "page-1", "title": "First Page", "text": "budget risk"},
            {"id": "page-2", "title": "Second Page", "text": "later content"},
        ]
        assert direct["entity_id"] == dispatched["entity_id"]
    finally:
        session.close()


def test_docs_search_projection_returns_none_for_missing_trashed_or_inactive_workspace_doc() -> (
    None
):
    session = _session()
    try:
        _add_workspace_user(session)
        session.commit()
        assert load_docs_search_document(session, "missing-doc") is None

        _add_native_doc(session, trashed_at=datetime(2026, 1, 3, tzinfo=UTC).replace(tzinfo=None))
        session.commit()
        assert load_docs_search_document(session, "doc-1") is None
    finally:
        session.close()

    inactive_session = _session()
    try:
        _add_workspace_user(inactive_session, workspace_active=False)
        _add_native_doc(inactive_session)
        inactive_session.commit()
        assert load_docs_search_document(inactive_session, "doc-1") is None
    finally:
        inactive_session.close()
