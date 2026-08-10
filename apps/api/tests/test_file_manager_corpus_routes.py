from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import auth_headers, create_workspace_user_session, dev_login

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
)


_FILES_BASE = "/api/v1/workspaces/administrator/files"


def test_file_corpus_admin_can_create_list_and_transition(client: TestClient) -> None:
    admin = dev_login(client, "administrator")
    headers = auth_headers(admin["token"])

    created = _create_corpus(client, headers=headers, name="AI TFT migration corpus")

    listed_response = client.get(f"{_FILES_BASE}/corpora", headers=headers)
    assert listed_response.status_code == 200, listed_response.text
    listed = {item["id"]: item for item in listed_response.json()}
    assert listed[created["id"]] == created

    transition_response = client.post(
        f"{_FILES_BASE}/corpora/{created['id']}/transition",
        headers=headers,
        json={
            "expected_metadata_version": 1,
            "access_scope_kind": "company",
            "reason": "Make the indexed corpus available to all company users",
            "request_id": "test-company-transition",
        },
    )
    assert transition_response.status_code == 200, transition_response.text
    transitioned = transition_response.json()
    assert transitioned["id"] == created["id"]
    assert transitioned["retrieval_partition_id"] == created["retrieval_partition_id"]
    assert transitioned["managed_workspace_id"] == created["managed_workspace_id"]
    assert transitioned["access_scope_kind"] == "company"
    assert transitioned["metadata_version"] == 2


def test_file_corpus_management_denies_non_admin_workspace_member(
    client: TestClient,
) -> None:
    admin = dev_login(client, "administrator")
    admin_headers = auth_headers(admin["token"])
    corpus = _create_corpus(client, headers=admin_headers, name="Admin-only corpus")
    member = create_workspace_user_session(
        client,
        workspace_key="administrator",
        login_id="filecorpusmember",
        email="file-corpus-member@ai-do.local",
        full_name="File Corpus Member",
        role="member",
    )
    member_headers = auth_headers(member["token"])

    transition_response = client.post(
        f"{_FILES_BASE}/corpora/{corpus['id']}/transition",
        headers=admin_headers,
        json={
            "expected_metadata_version": 1,
            "access_scope_kind": "company",
            "reason": "Publish before checking mutation authorization",
        },
    )
    assert transition_response.status_code == 200, transition_response.text

    responses = [
        client.get(f"{_FILES_BASE}/corpora", headers=member_headers),
        client.post(
            f"{_FILES_BASE}/corpora",
            headers=member_headers,
            json={"name": "Forbidden corpus"},
        ),
        client.post(
            f"{_FILES_BASE}/corpora/{corpus['id']}/transition",
            headers=member_headers,
            json={
                "expected_metadata_version": 1,
                "access_scope_kind": "company",
                "reason": "Member must not manage corpus scope",
            },
        ),
        client.post(
            f"{_FILES_BASE}/upload",
            headers=member_headers,
            data={"visibility": "workspace", "corpus_id": corpus["id"]},
            files={"file": ("unapproved.txt", b"unapproved", "text/plain")},
        ),
    ]

    for response in responses:
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "files.corpus_access_required"


def test_folder_and_upload_routes_persist_explicit_corpus_id(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    admin = dev_login(client, "administrator")
    headers = auth_headers(admin["token"])
    corpus = _create_corpus(client, headers=headers, name="Files route corpus")

    folder_response = client.post(
        f"{_FILES_BASE}/folders",
        headers=headers,
        json={
            "name": "Corpus root",
            "visibility": "private",
            "corpus_id": corpus["id"],
        },
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()
    assert folder["corpus_id"] == corpus["id"]
    assert folder["visibility"] == "workspace"

    upload_response = client.post(
        f"{_FILES_BASE}/upload",
        headers=headers,
        data={
            "visibility": "private",
            "corpus_id": corpus["id"],
        },
        files={"file": ("corpus-source.txt", b"indexed corpus source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert uploaded["corpus_id"] == corpus["id"]
    assert uploaded["visibility"] == "workspace"

    with get_session_factory()() as db:
        stored_corpus = db.get(FileManagerCorpus, corpus["id"])
        stored_folder = db.get(FileManagerFolder, folder["id"])
        stored_file = db.get(FileManagerFile, uploaded["id"])
        assert stored_corpus is not None
        assert stored_folder is not None
        assert stored_file is not None
        assert stored_folder.corpus_id == stored_file.corpus_id == stored_corpus.id
        assert {
            str(stored_folder.retrieval_partition_id),
            str(stored_file.retrieval_partition_id),
        } == {str(stored_corpus.retrieval_partition_id)}


def _create_corpus(
    client: TestClient,
    *,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = client.post(
        f"{_FILES_BASE}/corpora",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    corpus = response.json()
    assert corpus["name"] == name
    assert corpus["access_scope_kind"] == "workspace"
    assert corpus["metadata_version"] == 1
    assert corpus["retrieval_partition_id"]
    return corpus
