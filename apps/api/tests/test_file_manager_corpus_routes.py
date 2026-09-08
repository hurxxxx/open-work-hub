from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import auth_headers, create_company_user_session, dev_login

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
)


_FILES_BASE = "/api/v1/files"


def test_file_corpus_admin_can_create_list_with_immutable_company_scope(client: TestClient) -> None:
    admin = dev_login(client, "administrator")
    headers = auth_headers(admin["token"])
    created = _create_corpus(client, headers=headers, name="Company records")
    response = client.get(f"{_FILES_BASE}/corpora", headers=headers)
    assert response.status_code == 200, response.text
    assert {item["id"]: item for item in response.json()}[created["id"]] == created
    obsolete = client.post(
        f"{_FILES_BASE}/corpora/{created['id']}/transition",
        headers=headers,
        json={"access_scope_kind": "personal", "expected_metadata_version": 1},
    )
    assert obsolete.status_code == 404
    with get_session_factory()() as db:
        corpus = db.get(FileManagerCorpus, created["id"])
        assert corpus.access_scope_kind == "company"
        assert corpus.metadata_version == 1


def test_file_corpus_management_denies_non_admin_company_user(client: TestClient) -> None:
    admin = dev_login(client, "administrator")
    corpus = _create_corpus(client, headers=auth_headers(admin["token"]), name="Admin-only corpus")
    member = create_company_user_session(
        client,
        login_id="filecorpusmember",
        email="file-corpus-member@example.test",
        full_name="File Corpus Member",
    )
    headers = auth_headers(member["token"])
    responses = [
        client.get(f"{_FILES_BASE}/corpora", headers=headers),
        client.post(f"{_FILES_BASE}/corpora", headers=headers, json={"name": "Denied"}),
        client.post(
            f"{_FILES_BASE}/upload",
            headers=headers,
            data={
                "visibility": "company",
                "company_admin_read_acknowledged": True,
                "corpus_id": corpus["id"],
            },
            files={"file": ("denied.txt", b"denied", "text/plain")},
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
            "company_admin_read_acknowledged": True,
            "corpus_id": corpus["id"],
        },
    )
    assert folder_response.status_code == 201, folder_response.text
    folder = folder_response.json()
    assert folder["corpus_id"] == corpus["id"]
    assert folder["visibility"] == "company"

    upload_response = client.post(
        f"{_FILES_BASE}/upload",
        headers=headers,
        data={
            "visibility": "private",
            "company_admin_read_acknowledged": True,
            "corpus_id": corpus["id"],
        },
        files={"file": ("corpus-source.txt", b"indexed corpus source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    assert uploaded["corpus_id"] == corpus["id"]
    assert uploaded["visibility"] == "company"

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
    assert corpus["access_scope_kind"] == "company"
    assert corpus["metadata_version"] == 1
    assert corpus["retrieval_partition_id"]
    return corpus
