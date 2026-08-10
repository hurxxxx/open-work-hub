from __future__ import annotations

from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select

from dev_accounts import create_workspace_user_session, dev_login

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from open_alm_api.domains.files import (
    rag_projection,
    rag_status,
    rag_sync,
    search_hooks,
    service as files_service,
)
from open_alm_api.domains.files.models import FileManagerFile, FileManagerStorageCleanupJob
from open_alm_api.domains.files.rag_projection import FileExtractionArtifact
from open_alm_api.domains.rag.models import RagSyncJob
from open_alm_api.domains.rag.runtime import (
    PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_alm_api.domains.retrieval.models import (
    RetrievalProjectionEvent,
    RetrievalProjectionGeneration,
)
from open_alm_api.domains.retrieval.projection_fencing import record_projection_event
from open_alm_api.domains.search.models import SearchIndexJob
from open_alm_api.domains.search.index_gateway import (
    RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
)
from open_alm_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _administrator_member_session(client: TestClient, login_id: str) -> dict:
    return create_workspace_user_session(
        client,
        workspace_key="administrator",
        login_id=login_id,
        email=f"{login_id}@open-alm.local",
        full_name="Administrator Workspace Member",
    )


@pytest.mark.external_integration("minio")
def test_file_manager_upload_download_and_delete_with_rag_job(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise the post-generation lifecycle explicitly. Runtime Files
    # retrieval remains fail-closed until the isolated backend cutover.
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_status, "FILES_RETRIEVAL_ACTIVE", True)
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    folder_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=headers,
        json={"name": "Policies", "visibility": "workspace"},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()
    assert folder["name"] == "Policies"
    assert folder["visibility"] == "workspace"

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"folder_id": folder["id"], "visibility": "workspace"},
        files={"file": ("policy.txt", b"plain file storage", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()
    assert file["filename"] == "policy.txt"
    assert file["folder_id"] == folder["id"]
    assert file["visibility"] == "workspace"
    assert file["rag_status"] == "pending"
    assert file["rag_updated_at"] is not None

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=headers,
        params={"folder_id": folder["id"]},
    )
    assert browse_response.status_code == 200, browse_response.text
    browse = browse_response.json()
    assert browse["current_folder"]["id"] == folder["id"]
    assert browse["files"][0]["id"] == file["id"]

    download_response = client.get(
        f"/api/v1/workspaces/administrator/files/{file['id']}/download",
        headers=headers,
    )
    assert download_response.status_code == 200, download_response.text
    download_url = download_response.json()["url"]
    assert download_url.startswith(f"/api/v1/files/content/{file['id']}?")
    assert "127.0.0.1" not in download_url

    content_response = client.get(download_url)
    assert content_response.status_code == 200, content_response.text
    assert content_response.content == b"plain file storage"
    assert content_response.headers["content-type"].startswith("text/plain")
    assert content_response.headers["content-disposition"].startswith("attachment;")
    assert "policy.txt" in content_response.headers["content-disposition"]

    with get_session_factory()() as db:
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == file["id"]))
        assert rag_job is not None
        assert rag_job.operation == "upsert"

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/files/{file['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    with get_session_factory()() as db:
        row = db.get(FileManagerFile, file["id"])
        assert row is not None
        assert row.deleted_at is not None


def test_file_manager_reports_rag_status_until_both_indexes_are_ready(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_status, "FILES_RETRIEVAL_ACTIVE", True)
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])
    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("rag-status.txt", b"heater retrieval status", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert uploaded["rag_status"] == "pending"

    with get_session_factory()() as db:
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == uploaded["id"]))
        assert rag_job is not None
        rag_job.status = "processing"
        db.commit()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=headers,
    )
    assert browse_response.status_code == 200, browse_response.text
    assert browse_response.json()["files"][0]["rag_status"] == "processing"

    with get_session_factory()() as db:
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == uploaded["id"]))
        row = db.get(FileManagerFile, uploaded["id"])
        assert rag_job is not None and row is not None
        rag_job.status = "succeeded"
        row.extraction_status = "ready"
        row.extraction_content_checksum = "a" * 64
        row.extraction_text = "heater retrieval status"
        row.extraction_blocks = [{"text": "heater retrieval status"}]
        search_job = SearchIndexJob(
            id="file-rag-status-search-job",
            workspace_id=row.workspace_id,
            entity_type="file",
            entity_id=row.id,
            operation="upsert",
            status="pending",
            resource_type=rag_job.resource_type,
            retrieval_partition_id=rag_job.retrieval_partition_id,
            projection_event_sequence=rag_job.projection_event_sequence,
            projection_version=rag_job.projection_version,
            desired_state=rag_job.desired_state,
        )
        db.add(search_job)
        db.commit()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=headers,
    )
    assert browse_response.status_code == 200, browse_response.text
    assert browse_response.json()["files"][0]["rag_status"] == "processing"

    with get_session_factory()() as db:
        search_job = db.get(SearchIndexJob, "file-rag-status-search-job")
        assert search_job is not None
        search_job.status = "succeeded"
        db.commit()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=headers,
    )
    assert browse_response.status_code == 200, browse_response.text
    file_item = browse_response.json()["files"][0]
    assert file_item["rag_status"] == "ready"
    assert "extraction_error_code" not in file_item

    with get_session_factory()() as db:
        row = db.get(FileManagerFile, uploaded["id"])
        assert row is not None
        row.extraction_status = "unsupported"
        row.extraction_error_code = "unsupported_content_signature"
        db.commit()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=headers,
    )
    assert browse_response.status_code == 200, browse_response.text
    unsupported_item = browse_response.json()["files"][0]
    assert unsupported_item["rag_status"] == "unsupported"
    assert "extraction_error_code" not in unsupported_item


def test_file_manager_reports_adopted_file_ready_when_active_pair_covers_current_event(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_status, "FILES_RETRIEVAL_ACTIVE", True)
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])
    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("adopted-ready.txt", b"adopted generation status", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    settings = get_settings()
    cohort = "file_status_adoption_test"
    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "d" * 64
        file.extraction_text = "adopted generation status"
        file.extraction_blocks = [{"text": "adopted generation status"}]
        assert file.retrieval_partition_id is not None
        repair_event = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            retrieval_partition_id=file.retrieval_partition_id,
            change_kind="repair",
            desired_state="active",
            content_checksum=file.extraction_content_checksum,
            diagnostic_workspace_id=file.workspace_id,
            trace_context={"reconciliation": "legacy_files_adoption"},
        )
        db.execute(delete(RagSyncJob).where(RagSyncJob.resource_id == uploaded["id"]))
        db.execute(delete(SearchIndexJob).where(SearchIndexJob.entity_id == uploaded["id"]))
        event = db.scalar(
            select(RetrievalProjectionEvent).where(
                RetrievalProjectionEvent.event_sequence == repair_event.event_sequence
            )
        )
        assert event is not None
        validated_at = datetime(2026, 7, 23, 1, 0, 0)
        validation_details = {
            "release_cohort": cohort,
            "included_resource_types": ["file_manager_file"],
        }
        db.add_all(
            [
                RetrievalProjectionGeneration(
                    id="9d02d038-352e-4ca3-9675-52853c555ce1",
                    backend="opensearch",
                    generation_key=cohort,
                    physical_name=keyword_search_partitioned_index_name(
                        settings.opensearch_index_prefix,
                        generation=cohort,
                    ),
                    alias_name=keyword_search_partitioned_index_alias(
                        settings.opensearch_index_prefix
                    ),
                    schema_version=RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
                    state="active",
                    baseline_event_sequence=0,
                    replay_event_sequence=event.event_sequence,
                    validation_state="passed",
                    validation_details=validation_details,
                    validated_at=validated_at,
                ),
                RetrievalProjectionGeneration(
                    id="c742334e-51ea-449e-a658-058ed3561baf",
                    backend="qdrant",
                    generation_key=cohort,
                    physical_name=resolve_partitioned_rag_collection_name(
                        settings,
                        generation=cohort,
                    ),
                    alias_name=resolve_partitioned_rag_collection_alias(settings),
                    schema_version=PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
                    state="active",
                    baseline_event_sequence=0,
                    replay_event_sequence=event.event_sequence,
                    validation_state="passed",
                    validation_details=validation_details,
                    validated_at=validated_at,
                ),
            ]
        )
        repair_event_sequence = event.event_sequence
        partition_id = event.retrieval_partition_id
        projection_version = event.projection_version
        workspace_id = file.workspace_id
        db.commit()

    def _browse_status() -> str:
        browse_response = client.get(
            "/api/v1/workspaces/administrator/files",
            headers=headers,
        )
        assert browse_response.status_code == 200, browse_response.text
        files_by_id = {item["id"]: item for item in browse_response.json()["files"]}
        return files_by_id[uploaded["id"]]["rag_status"]

    assert _browse_status() == "ready"

    with get_session_factory()() as db:
        qdrant = db.get(
            RetrievalProjectionGeneration,
            "c742334e-51ea-449e-a658-058ed3561baf",
        )
        assert qdrant is not None
        qdrant.replay_event_sequence = repair_event_sequence - 1
        db.commit()
    assert _browse_status() == "pending"

    with get_session_factory()() as db:
        qdrant = db.get(
            RetrievalProjectionGeneration,
            "c742334e-51ea-449e-a658-058ed3561baf",
        )
        assert qdrant is not None
        qdrant.replay_event_sequence = repair_event_sequence
        qdrant.validation_state = "pending"
        db.commit()
    assert _browse_status() == "pending"

    with get_session_factory()() as db:
        qdrant = db.get(
            RetrievalProjectionGeneration,
            "c742334e-51ea-449e-a658-058ed3561baf",
        )
        assert qdrant is not None
        qdrant.validation_state = "passed"
        qdrant.state = "retired"
        db.commit()
    assert _browse_status() == "pending"

    with get_session_factory()() as db:
        qdrant = db.get(
            RetrievalProjectionGeneration,
            "c742334e-51ea-449e-a658-058ed3561baf",
        )
        file = db.get(FileManagerFile, uploaded["id"])
        assert qdrant is not None and file is not None
        qdrant.state = "active"
        file.extraction_content_checksum = "e" * 64
        db.commit()
    assert _browse_status() == "pending"

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_content_checksum = "d" * 64
        db.add(
            RagSyncJob(
                id="file-status-covered-current-failed",
                scope_kind="workspace",
                workspace_id=workspace_id,
                retrieval_partition_id=partition_id,
                projection_event_sequence=repair_event_sequence,
                projection_version=projection_version,
                desired_state="active",
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                resource_id=uploaded["id"],
                operation="upsert",
                content_checksum="d" * 64,
                status="failed",
            )
        )
        db.commit()
    assert _browse_status() == "failed"

    with get_session_factory()() as db:
        db.execute(delete(RagSyncJob).where(RagSyncJob.resource_id == uploaded["id"]))
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "failed"
        file.extraction_content_checksum = None
        db.commit()
    assert _browse_status() == "failed"


def test_file_corpus_workspace_move_preserves_ready_projection_status(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_status, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_sync, "get_settings", lambda: SimpleNamespace(rag_enabled=True))
    administrator = dev_login(client, "administrator")
    admin_headers = _auth_headers(administrator["token"])
    target_member = dev_login(client, "delivery-hub-member")
    target_headers = _auth_headers(target_member["token"])

    corpus_response = client.post(
        "/api/v1/workspaces/administrator/files/corpora",
        headers=admin_headers,
        json={"name": "Move-ready corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()
    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=admin_headers,
        data={"corpus_id": corpus["id"], "visibility": "workspace"},
        files={"file": ("move-ready.txt", b"stable projection", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == uploaded["id"]))
        target_workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert file is not None and rag_job is not None and target_workspace is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "c" * 64
        file.extraction_text = "stable projection"
        file.extraction_blocks = [{"text": "stable projection"}]
        rag_job.status = "succeeded"
        db.add(
            SearchIndexJob(
                id="file-move-ready-search-job",
                workspace_id=file.workspace_id,
                entity_type="file",
                entity_id=file.id,
                operation="upsert",
                status="succeeded",
                resource_type=rag_job.resource_type,
                retrieval_partition_id=rag_job.retrieval_partition_id,
                projection_event_sequence=rag_job.projection_event_sequence,
                projection_version=rag_job.projection_version,
                desired_state=rag_job.desired_state,
            )
        )
        target_workspace_id = target_workspace.id
        db.commit()

    transition_response = client.post(
        f"/api/v1/workspaces/administrator/files/corpora/{corpus['id']}/transition",
        headers=admin_headers,
        json={
            "expected_metadata_version": corpus["metadata_version"],
            "access_scope_kind": "workspace",
            "target_workspace_id": target_workspace_id,
            "reason": "Verify ready state survives a metadata-only move",
        },
    )
    assert transition_response.status_code == 200, transition_response.text

    browse_response = client.get(
        "/api/v1/workspaces/delivery-hub/files",
        headers=target_headers,
    )
    assert browse_response.status_code == 200, browse_response.text
    moved = next(item for item in browse_response.json()["files"] if item["id"] == uploaded["id"])
    assert moved["rag_status"] == "ready"


def test_active_files_gate_enqueues_lifecycle_jobs_and_purges_extraction(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(search_hooks, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(rag_sync, "get_settings", lambda: SimpleNamespace(rag_enabled=True))
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("rag-lifecycle.txt", b"heater lifecycle", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file_id = upload_response.json()["id"]

    with get_session_factory()() as db:
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == file_id))
        assert rag_job is not None
        assert rag_job.operation == "upsert"
        row = db.get(FileManagerFile, file_id)
        assert row is not None
        row.extraction_status = "ready"
        row.extraction_content_checksum = "a" * 64
        row.extraction_text = "민감한 히터 검색 본문"
        row.extraction_blocks = [{"text": "민감한 히터 검색 본문"}]
        row.extraction_metadata = {"parser": "plain_text"}
        db.commit()

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/files/{file_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    with get_session_factory()() as db:
        rag_job = db.scalar(select(RagSyncJob).where(RagSyncJob.resource_id == file_id))
        search_job = db.scalar(select(SearchIndexJob).where(SearchIndexJob.entity_id == file_id))
        row = db.get(FileManagerFile, file_id)
        assert rag_job is not None and rag_job.operation == "delete"
        assert search_job is not None and search_job.operation == "delete"
        assert row is not None and row.deleted_at is not None
        assert row.extraction_text is None
        assert row.extraction_blocks == []
        assert row.extraction_metadata == {}
        row.extraction_status = "ready"
        row.extraction_text = "late worker residue"
        row.extraction_blocks = [{"text": "late worker residue"}]
        row.extraction_metadata = {"parser": "late-worker"}
        db.flush()
        rag_sync.mark_file_projection_deleted(db, file_id=file_id)
        db.commit()
        db.refresh(row)
        assert row.extraction_text is None
        assert row.extraction_blocks == []
        assert row.extraction_metadata == {}


def test_extraction_result_cannot_be_persisted_after_concurrent_soft_delete(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])
    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("concurrent-delete.txt", b"heater content", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file_id = upload_response.json()["id"]

    worker_db = get_session_factory()()
    try:
        stale_file = worker_db.get(FileManagerFile, file_id)
        assert stale_file is not None and stale_file.deleted_at is None
        delete_response = client.delete(
            f"/api/v1/workspaces/administrator/files/{file_id}",
            headers=headers,
        )
        assert delete_response.status_code == 204, delete_response.text

        stored = rag_projection._store_artifact_if_active(
            worker_db,
            file_id=file_id,
            artifact=FileExtractionArtifact(
                content_checksum="a" * 64,
                text="late sensitive extraction",
                blocks=[],
                metadata={"parser": "plain_text"},
            ),
        )
        worker_db.commit()
        assert stored is False
    finally:
        worker_db.close()

    with get_session_factory()() as db:
        row = db.get(FileManagerFile, file_id)
        assert row is not None and row.deleted_at is not None
        assert row.extraction_text is None
        assert row.extraction_blocks == []
        assert row.extraction_metadata == {}


def test_file_manager_image_preview_uses_inline_same_origin_content_url(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("diagram.png", b"\x89PNG\r\n\x1a\npng-bytes", "image/png")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()

    preview_response = client.get(
        f"/api/v1/workspaces/administrator/files/{file['id']}/preview",
        headers=headers,
    )
    assert preview_response.status_code == 200, preview_response.text
    preview_url = preview_response.json()["url"]
    assert preview_url.startswith(f"/api/v1/files/content/{file['id']}?")
    assert "127.0.0.1" not in preview_url

    content_response = client.get(preview_url)
    assert content_response.status_code == 200, content_response.text
    assert content_response.content == b"\x89PNG\r\n\x1a\npng-bytes"
    assert content_response.headers["content-type"].startswith("image/png")
    assert content_response.headers["content-disposition"].startswith("inline;")
    assert "diagram.png" in content_response.headers["content-disposition"]


def test_workspace_shared_file_is_readable_but_not_deletable_by_member(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    admin_session = dev_login(client, "administrator")
    member_session = _administrator_member_session(client, "filesmember")

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=_auth_headers(admin_session["token"]),
        data={"visibility": "workspace"},
        files={"file": ("shared.txt", b"shared", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=_auth_headers(member_session["token"]),
    )
    assert browse_response.status_code == 200, browse_response.text
    assert file["id"] in {item["id"] for item in browse_response.json()["files"]}

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/files/{file['id']}",
        headers=_auth_headers(member_session["token"]),
    )
    assert delete_response.status_code == 403, delete_response.text


def test_child_folder_and_upload_inherit_parent_visibility(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    parent_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=headers,
        json={"name": "Shared root", "visibility": "workspace"},
    )
    assert parent_response.status_code == 201, parent_response.text
    parent = parent_response.json()
    assert parent["visibility"] == "workspace"

    child_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=headers,
        json={
            "name": "Child",
            "parent_id": parent["id"],
            "visibility": "private",
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()
    assert child["visibility"] == "workspace"

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"folder_id": child["id"], "visibility": "private"},
        files={"file": ("inherited.txt", b"inherited", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()
    assert file["visibility"] == "workspace"


def test_folder_visibility_changes_are_rejected(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    folder_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=headers,
        json={"name": "Stable visibility", "visibility": "private"},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()

    update_response = client.patch(
        f"/api/v1/workspaces/administrator/files/folders/{folder['id']}",
        headers=headers,
        json={"visibility": "workspace"},
    )
    assert update_response.status_code == 422
    assert update_response.json()["code"] == "files.visibility_change_not_allowed"


def test_private_file_is_hidden_from_workspace_member(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    admin_session = dev_login(client, "administrator")
    member_session = _administrator_member_session(client, "filesprivateviewer")

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=_auth_headers(admin_session["token"]),
        data={"visibility": "private"},
        files={"file": ("private.txt", b"private", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()

    browse_response = client.get(
        "/api/v1/workspaces/administrator/files",
        headers=_auth_headers(member_session["token"]),
    )
    assert browse_response.status_code == 200, browse_response.text
    assert file["id"] not in {item["id"] for item in browse_response.json()["files"]}

    download_response = client.get(
        f"/api/v1/workspaces/administrator/files/{file['id']}/download",
        headers=_auth_headers(member_session["token"]),
    )
    assert download_response.status_code == 403, download_response.text


def test_signed_file_content_rechecks_workspace_membership(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    admin_session = dev_login(client, "administrator")
    member_session = _administrator_member_session(client, "filesurlrevoked")
    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=_auth_headers(admin_session["token"]),
        data={"visibility": "workspace"},
        files={"file": ("revocable.txt", b"revocable", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file_id = upload_response.json()["id"]
    download_response = client.get(
        f"/api/v1/workspaces/administrator/files/{file_id}/download",
        headers=_auth_headers(member_session["token"]),
    )
    assert download_response.status_code == 200, download_response.text
    content_url = download_response.json()["url"]

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.login_id == "filesurlrevoked"))
        assert user is not None
        binding = db.scalar(
            select(WorkspaceUserBinding).where(WorkspaceUserBinding.user_id == user.id)
        )
        assert binding is not None
        db.delete(binding)
        db.commit()

    content_response = client.get(content_url)

    assert content_response.status_code == 403, content_response.text
    assert content_response.json()["code"] == "files.file_access_required"


def test_file_manager_archive_and_bulk_delete_selected_items(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    folder_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=headers,
        json={"name": "Project", "visibility": "private"},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()

    root_upload = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("root.txt", b"root", "text/plain")},
    )
    assert root_upload.status_code == 201, root_upload.text
    root_file = root_upload.json()

    nested_upload = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"folder_id": folder["id"], "visibility": "private"},
        files={"file": ("nested.txt", b"nested", "text/plain")},
    )
    assert nested_upload.status_code == 201, nested_upload.text
    nested_file = nested_upload.json()

    archive_response = client.post(
        "/api/v1/workspaces/administrator/files/archive",
        headers=headers,
        json={"file_ids": [root_file["id"]], "folder_ids": [folder["id"]]},
    )
    assert archive_response.status_code == 200, archive_response.text
    assert archive_response.headers["content-type"].startswith("application/zip")

    with ZipFile(BytesIO(archive_response.content)) as archive:
        assert archive.read("root.txt") == b"root"
        assert archive.read("Project/nested.txt") == b"nested"

    delete_response = client.post(
        "/api/v1/workspaces/administrator/files/bulk-delete",
        headers=headers,
        json={"file_ids": [root_file["id"]], "folder_ids": [folder["id"]]},
    )
    assert delete_response.status_code == 204, delete_response.text

    with get_session_factory()() as db:
        root_row = db.get(FileManagerFile, root_file["id"])
        nested_row = db.get(FileManagerFile, nested_file["id"])
        assert root_row is not None
        assert nested_row is not None
        assert root_row.deleted_at is not None
        assert nested_row.deleted_at is not None


def test_upload_rejects_stream_once_file_size_limit_is_exceeded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])
    monkeypatch.setattr(files_service, "MAX_FILE_UPLOAD_SIZE", 4)

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("too-big.txt", b"12345", "text/plain")},
    )

    assert upload_response.status_code == 413
    assert upload_response.json()["code"] == "files.file_size_limit_exceeded"
    with get_session_factory()() as db:
        assert (
            db.scalar(select(FileManagerFile).where(FileManagerFile.filename == "too-big.txt"))
            is None
        )


def test_archive_sanitizes_windows_paths_and_rejects_large_expansions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    first_upload = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("..\\evil.txt", b"safe", "text/plain")},
    )
    assert first_upload.status_code == 201, first_upload.text
    first_file = first_upload.json()
    assert first_file["filename"] == "evil.txt"

    archive_response = client.post(
        "/api/v1/workspaces/administrator/files/archive",
        headers=headers,
        json={"file_ids": [first_file["id"]]},
    )
    assert archive_response.status_code == 200, archive_response.text
    with ZipFile(BytesIO(archive_response.content)) as archive:
        assert archive.namelist() == ["evil.txt"]
        assert archive.read("evil.txt") == b"safe"

    second_upload = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("second.txt", b"second", "text/plain")},
    )
    assert second_upload.status_code == 201, second_upload.text
    monkeypatch.setattr(files_service, "MAX_ARCHIVE_FILE_COUNT", 1)

    limited_response = client.post(
        "/api/v1/workspaces/administrator/files/archive",
        headers=headers,
        json={"file_ids": [first_file["id"], second_upload.json()["id"]]},
    )
    assert limited_response.status_code == 413
    assert limited_response.json()["code"] == "files.archive_limit_exceeded"


def test_workspace_member_cannot_write_inside_owner_shared_folder(
    client: TestClient,
) -> None:
    admin_session = dev_login(client, "administrator")
    member_session = _administrator_member_session(client, "filesfoldermember")

    folder_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "Shared owner folder", "visibility": "workspace"},
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()

    create_child_response = client.post(
        "/api/v1/workspaces/administrator/files/folders",
        headers=_auth_headers(member_session["token"]),
        json={
            "name": "Member child",
            "parent_id": folder["id"],
            "visibility": "private",
        },
    )
    assert create_child_response.status_code == 403
    assert create_child_response.json()["code"] == "files.parent_manage_access_required"

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=_auth_headers(member_session["token"]),
        data={"folder_id": folder["id"], "visibility": "private"},
        files={"file": ("member.txt", b"member", "text/plain")},
    )
    assert upload_response.status_code == 403
    assert upload_response.json()["code"] == "files.parent_manage_access_required"


def test_delete_queues_storage_cleanup_job_when_minio_delete_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = _auth_headers(session["token"])

    upload_response = client.post(
        "/api/v1/workspaces/administrator/files/upload",
        headers=headers,
        data={"visibility": "private"},
        files={"file": ("cleanup.txt", b"cleanup", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file = upload_response.json()

    def fail_remove(keys):
        return [
            files_service.file_storage.FileStorageRemovalFailure(
                storage_key=key,
                exc=RuntimeError(f"cannot remove {key}"),
            )
            for key in keys
        ]

    monkeypatch.setattr(files_service.file_storage, "remove_file_objects", fail_remove)

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/files/{file['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    with get_session_factory()() as db:
        job = db.scalar(select(FileManagerStorageCleanupJob))
        assert job is not None
        assert job.storage_key.endswith("/cleanup.txt")
        assert job.status == "pending"
