from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.docs import partitioning as docs_partitioning
from open_work_hub_api.domains.docs import rag_sync as docs_rag_sync
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
)
from open_work_hub_api.domains.retrieval.partitioning import (
    RetrievalPartitionConflict,
    RetrievalPartitionUnbound,
)
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_work_hub_api.domains.source_access import SourceAclPolicy
from open_work_hub_api.domains.source_access.resource_types import NATIVE_DOC_RESOURCE_TYPE


def _job_rows() -> list[RagSyncJob]:
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(RagSyncJob).order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc())
            )
        )


def _visibility_job_rows() -> list[RagVisibilityRecomputeJob]:
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(RagVisibilityRecomputeJob).order_by(
                    RagVisibilityRecomputeJob.created_at.asc(),
                    RagVisibilityRecomputeJob.id.asc(),
                )
            )
        )


def _enable_docs_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        docs_rag_sync,
        "get_settings",
        lambda: SimpleNamespace(rag_enabled=True),
    )


def test_native_doc_sync_records_one_event_shared_by_search_and_rag(monkeypatch) -> None:
    projection_event = ProjectionEventRef(
        event_sequence=11,
        resource_type="docs_native_doc",
        resource_id="doc-1",
        projection_version=2,
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
        change_kind="delete",
        desired_state="deleted",
        content_checksum=None,
        visibility_checksum=None,
        diagnostic_workspace_id="ws-1",
    )
    recorded: list[dict] = []
    search_deliveries: list[dict] = []
    rag_deliveries: list[dict] = []
    monkeypatch.setattr(
        docs_rag_sync,
        "ensure_native_doc_partition",
        lambda *_args, **_kwargs: projection_event.retrieval_partition_id,
    )
    monkeypatch.setattr(
        docs_rag_sync,
        "record_projection_event",
        lambda *_args, **kwargs: recorded.append(kwargs) or projection_event,
    )
    monkeypatch.setattr(
        docs_rag_sync,
        "enqueue_doc_search_index",
        lambda *_args, **kwargs: search_deliveries.append(kwargs),
    )
    monkeypatch.setattr(
        docs_rag_sync,
        "enqueue_rag_sync_job",
        lambda *_args, **kwargs: rag_deliveries.append(kwargs),
    )
    _enable_docs_rag(monkeypatch)

    docs_rag_sync.enqueue_native_doc_rag_sync(
        object(),
        doc=SimpleNamespace(id="doc-1", workspace_id="ws-1"),
        operation=RagSyncOperation.DELETE,
    )

    assert recorded == [
        {
            "resource_type": "docs_native_doc",
            "resource_id": "doc-1",
            "retrieval_partition_id": projection_event.retrieval_partition_id,
            "change_kind": "delete",
            "desired_state": "deleted",
            "diagnostic_workspace_id": "ws-1",
        }
    ]
    assert search_deliveries[0]["projection_event"] is projection_event
    assert rag_deliveries[0]["projection_event"] is projection_event


def test_native_doc_scope_changes_keep_partition_and_advance_one_event_stream(client) -> None:
    from test_meeting import _auth_headers, _bootstrap_admin_session, _first_workspace_slug

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(admin_token),
        json={"title": "Stable partition doc", "rag_scope": "official"},
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()

    with get_session_factory()() as db:
        doc = db.get(NativeDoc, created["source_id"])
        assert doc is not None
        initial_partition_id = doc.retrieval_partition_id
        assert initial_partition_id is not None
        partition = db.get(RetrievalPartition, initial_partition_id)
        assert partition is not None
        assert partition.source_namespace == "docs"
        assert partition.managed_workspace_id == doc.workspace_id
        assert partition.candidate_scope_kind == "workspace"
        assert partition.candidate_workspace_id == doc.workspace_id
        assert partition.candidate_user_id is None

    personal_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{created['id']}",
        headers=_auth_headers(admin_token),
        json={"rag_scope": "personal"},
    )
    assert personal_response.status_code == 200, personal_response.text
    assert personal_response.json()["rag_scope"] == "personal"

    with get_session_factory()() as db:
        doc = db.get(NativeDoc, created["source_id"])
        user = db.get(User, admin["user"]["id"])
        assert doc is not None
        assert user is not None
        policy = SourceAclPolicy.for_workspace_id(
            db,
            workspace_id=doc.workspace_id,
            user=user,
        )
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, doc.id) is True
        assert policy.can_read_rag_resource(NATIVE_DOC_RESOURCE_TYPE, doc.id) is False

    official_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{created['id']}",
        headers=_auth_headers(admin_token),
        json={"rag_scope": "official"},
    )
    assert official_response.status_code == 200, official_response.text
    assert official_response.json()["rag_scope"] == "official"

    with get_session_factory()() as db:
        doc = db.get(NativeDoc, created["source_id"])
        user = db.get(User, admin["user"]["id"])
        assert doc is not None
        assert user is not None
        assert doc.retrieval_partition_id == initial_partition_id
        policy = SourceAclPolicy.for_workspace_id(
            db,
            workspace_id=doc.workspace_id,
            user=user,
        )
        assert policy.can_read_rag_resource(NATIVE_DOC_RESOURCE_TYPE, doc.id) is True
        events = list(
            db.scalars(
                select(RetrievalProjectionEvent)
                .where(
                    RetrievalProjectionEvent.resource_type == NATIVE_DOC_RESOURCE_TYPE,
                    RetrievalProjectionEvent.resource_id == doc.id,
                )
                .order_by(RetrievalProjectionEvent.projection_version.asc())
            )
        )

    assert [event.projection_version for event in events] == [1, 2, 3]
    assert [event.event_sequence for event in events] == sorted(
        event.event_sequence for event in events
    )
    assert {event.retrieval_partition_id for event in events} == {initial_partition_id}


def test_new_native_docs_use_workspace_partition_for_every_rag_scope(monkeypatch) -> None:
    requested: list[dict] = []
    monkeypatch.setattr(
        docs_partitioning,
        "ensure_default_partition",
        lambda *_args, **kwargs: requested.append(kwargs)
        or SimpleNamespace(id="11111111-1111-1111-1111-111111111111"),
    )

    class _Session:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value) -> None:
            self.added.append(value)

    docs = [
        SimpleNamespace(
            id=f"doc-{rag_scope}",
            workspace_id="ws-1",
            owner_id="user-1",
            rag_scope=rag_scope,
            retrieval_partition_id=None,
        )
        for rag_scope in ("official", "personal", "excluded")
    ]
    db = _Session()

    partition_ids = [
        docs_partitioning.ensure_native_doc_partition(db, doc=doc) for doc in docs
    ]

    assert partition_ids == ["11111111-1111-1111-1111-111111111111"] * 3
    assert [doc.retrieval_partition_id for doc in docs] == partition_ids
    assert db.added == docs
    assert requested == [
        {
            "source_namespace": "docs",
            "candidate_scope_kind": "workspace",
            "workspace_id": "ws-1",
        }
    ] * 3


@pytest.mark.parametrize(
    ("partition", "error_type"),
    [
        (None, RetrievalPartitionUnbound),
        (
            SimpleNamespace(
                source_namespace="files",
                managed_workspace_id="ws-1",
                candidate_scope_kind="workspace",
                candidate_workspace_id="ws-1",
                candidate_user_id=None,
                state="active",
                is_default_ingest=True,
            ),
            RetrievalPartitionConflict,
        ),
        (
            SimpleNamespace(
                source_namespace="docs",
                managed_workspace_id=None,
                candidate_scope_kind="personal",
                candidate_workspace_id=None,
                candidate_user_id="user-1",
                state="active",
                is_default_ingest=True,
            ),
            RetrievalPartitionConflict,
        ),
        (
            SimpleNamespace(
                source_namespace="docs",
                managed_workspace_id="ws-2",
                candidate_scope_kind="workspace",
                candidate_workspace_id="ws-2",
                candidate_user_id=None,
                state="active",
                is_default_ingest=True,
            ),
            RetrievalPartitionConflict,
        ),
        (
            SimpleNamespace(
                source_namespace="docs",
                managed_workspace_id="ws-1",
                candidate_scope_kind="workspace",
                candidate_workspace_id="ws-1",
                candidate_user_id=None,
                state="retired",
                is_default_ingest=True,
            ),
            RetrievalPartitionConflict,
        ),
        (
            SimpleNamespace(
                source_namespace="docs",
                managed_workspace_id="ws-1",
                candidate_scope_kind="workspace",
                candidate_workspace_id="ws-1",
                candidate_user_id=None,
                state="active",
                is_default_ingest=False,
            ),
            RetrievalPartitionConflict,
        ),
    ],
    ids=(
        "missing",
        "wrong-namespace",
        "personal",
        "wrong-workspace",
        "retired",
        "non-default",
    ),
)
def test_existing_native_doc_partition_must_be_valid_or_fail_closed(
    monkeypatch,
    partition,
    error_type,
) -> None:
    monkeypatch.setattr(
        docs_partitioning,
        "ensure_default_partition",
        lambda *_args, **_kwargs: pytest.fail("existing bindings must not be replaced"),
    )

    class _Session:
        added: list[object] = []

        def get(self, model, partition_id):
            assert model is RetrievalPartition
            assert partition_id == "11111111-1111-1111-1111-111111111111"
            return partition

        def add(self, value) -> None:
            self.added.append(value)

    db = _Session()
    doc = SimpleNamespace(
        id="doc-existing",
        workspace_id="ws-1",
        owner_id="user-1",
        rag_scope="official",
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
    )

    with pytest.raises(error_type):
        docs_partitioning.ensure_native_doc_partition(db, doc=doc)

    assert doc.retrieval_partition_id == "11111111-1111-1111-1111-111111111111"
    assert db.added == []


def test_meeting_doc_acl_changes_enqueue_rag_visibility_recompute_jobs(
    client,
    monkeypatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from test_meeting import (
        _auth_headers,
        _bootstrap_admin_session,
        _create_user_with_workspaces,
        _first_workspace_slug,
        _login,
    )

    _enable_docs_rag(monkeypatch)
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="meeting-rag-reader@open-work-hub.local",
        full_name="Meeting Rag Reader",
        workspace_keys=[workspace_slug],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    create_doc = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(admin_token),
        json={"title": "Meeting RAG Reference"},
    )
    assert create_doc.status_code == 201, create_doc.text
    doc = create_doc.json()
    doc_id = doc["source_id"]

    initial_recompute_jobs = [job for job in _visibility_job_rows() if job.scope_type == "meeting"]
    assert initial_recompute_jobs == []

    start_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)
    create_meeting = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(admin_token),
        json={
            "title": "Sprint planning",
            "agenda": "Discuss Q2 roadmap.",
            "start_at": start_at.isoformat(),
            "end_at": (start_at + timedelta(hours=1)).isoformat(),
            "attendees": [{"user_id": attendee["user"]["id"], "role": "required"}],
            "task_ids": [],
            "doc_ids": [doc_id],
        },
    )
    assert create_meeting.status_code == 201, create_meeting.text
    meeting = create_meeting.json()

    grant_jobs = [
        job
        for job in _visibility_job_rows()
        if job.scope_type == "meeting" and job.scope_id == meeting["id"]
    ]
    assert grant_jobs
    assert [
        job
        for job in _job_rows()
        if job.resource_id == doc_id and job.operation == "visibility_update"
    ] == []

    doc_lookup = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert doc_lookup.status_code == 200

    detach_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/docs/{doc_id}",
        headers=_auth_headers(admin_token),
    )
    assert detach_response.status_code == 200, detach_response.text

    revoke_jobs = [
        job
        for job in _visibility_job_rows()
        if job.scope_type == "meeting" and job.scope_id == meeting["id"]
    ]
    assert len(revoke_jobs) == 1
    assert revoke_jobs[0].id == grant_jobs[0].id
    assert revoke_jobs[0].cursor == {"doc_ids": [doc_id]}
