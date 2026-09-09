from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import content_headers
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.pms.attachments import normalize_task_attachment_filename
from open_work_hub_api.domains.pms.models import Attachment, TaskActivityLog
from test_pms_issues import (
    _add_task_list_member,
    _auth_headers,
    _bootstrap_admin,
    _create_issue,
    _create_task_list,
    _create_user,
    _login,
)


def test_task_attachment_upload_registers_canonical_storage_and_activity(
    client: TestClient,
    monkeypatch,
) -> None:
    store = _FakeTaskAttachmentStore()
    _install_fake_store(monkeypatch, store)
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    task = _create_issue(client, token, task_list["id"], title="Attachment task")

    response = client.post(
        f"/api/v1/pms/tasks/{task['id']}/attachments",
        headers=_auth_headers(token),
        files={"file": ("brief.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["filename"] == "brief.txt"
    assert payload["content_type"] == "text/plain"
    assert payload["size_bytes"] == 5
    assert payload["download_url"].startswith("/api/v1/content#grant=")
    assert "127.0.0.1" not in payload["download_url"]
    assert "fake-minio" not in payload["download_url"]
    assert store.puts == [
        {
            "storage_key": f"pms/{task_list['id']}/{task['id']}/{payload['id']}/brief.txt",
            "content": b"hello",
            "content_type": "text/plain",
        }
    ]

    download_response = client.get(
        payload["download_url"],
        headers=content_headers(token, payload["download_url"]),
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == b"hello"
    assert download_response.headers["content-type"].startswith("text/plain")
    assert "brief.txt" in download_response.headers["content-disposition"]

    with get_session_factory()() as db:
        attachment = db.get(Attachment, payload["id"])
        assert attachment is not None
        assert attachment.filename == "brief.txt"
        log = db.scalar(
            select(TaskActivityLog).where(
                TaskActivityLog.task_id == task["id"],
                TaskActivityLog.action == "attachment_added",
            )
        )
        assert log is not None
        assert "brief.txt" in log.message


def test_task_attachment_normalizes_missing_filename() -> None:
    assert normalize_task_attachment_filename(None) == "unnamed"
    assert normalize_task_attachment_filename("") == "unnamed"
    assert normalize_task_attachment_filename("  ") == "unnamed"
    assert normalize_task_attachment_filename(" brief.txt ") == "brief.txt"


def test_task_attachment_delete_tolerates_missing_storage_and_cleans_local_state(
    client: TestClient,
    monkeypatch,
) -> None:
    store = _FakeTaskAttachmentStore(remove_raises=True)
    _install_fake_store(monkeypatch, store)
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)
    task = _create_issue(client, token, task_list["id"], title="Delete attachment")
    upload = client.post(
        f"/api/v1/pms/tasks/{task['id']}/attachments",
        headers=_auth_headers(token),
        files={"file": ("delete-me.txt", b"payload", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment_id = upload.json()["id"]

    response = client.delete(
        f"/api/v1/pms/attachments/{attachment_id}",
        headers=_auth_headers(token),
    )

    assert response.status_code == 204, response.text
    assert store.removes == [store.puts[0]["storage_key"]]
    with get_session_factory()() as db:
        assert db.get(Attachment, attachment_id) is None
        log = db.scalar(
            select(TaskActivityLog).where(
                TaskActivityLog.task_id == task["id"],
                TaskActivityLog.action == "attachment_removed",
            )
        )
        assert log is not None
        assert "delete-me.txt" in log.message


def test_task_attachment_viewer_cannot_upload_or_delete(
    client: TestClient,
    monkeypatch,
) -> None:
    store = _FakeTaskAttachmentStore()
    _install_fake_store(monkeypatch, store)
    admin_token = _bootstrap_admin(client)
    task_list = _create_task_list(client, admin_token)
    task = _create_issue(client, admin_token, task_list["id"], title="Viewer attachment")
    upload = client.post(
        f"/api/v1/pms/tasks/{task['id']}/attachments",
        headers=_auth_headers(admin_token),
        files={"file": ("admin.txt", b"payload", "text/plain")},
    )
    assert upload.status_code == 201, upload.text

    viewer = _create_user(
        client,
        admin_token,
        email="attachment-viewer@open-work-hub.local",
        full_name="Attachment Viewer",
    )
    _add_task_list_member(client, admin_token, task_list["id"], viewer["user"]["id"], "viewer")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    viewer_upload = client.post(
        f"/api/v1/pms/tasks/{task['id']}/attachments",
        headers=_auth_headers(viewer_token),
        files={"file": ("viewer.txt", b"payload", "text/plain")},
    )
    viewer_delete = client.delete(
        f"/api/v1/pms/attachments/{upload.json()['id']}",
        headers=_auth_headers(viewer_token),
    )

    assert viewer_upload.status_code == 403
    assert viewer_delete.status_code == 403


def _install_fake_store(monkeypatch, store: "_FakeTaskAttachmentStore") -> None:
    from open_work_hub_api.domains.pms import attachments

    monkeypatch.setattr(attachments, "task_attachment_object_store", lambda: store)


class _FakeTaskAttachmentStore:
    def __init__(self, *, remove_raises: bool = False) -> None:
        self.remove_raises = remove_raises
        self.puts: list[dict] = []
        self.removes: list[str] = []

    def put(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        self.puts.append(
            {
                "storage_key": storage_key,
                "content": content,
                "content_type": content_type,
            }
        )

    def remove(self, *, storage_key: str) -> None:
        self.removes.append(storage_key)
        if self.remove_raises:
            raise FileNotFoundError(storage_key)

    def open_stream(self, *, storage_key: str, chunk_size: int):
        del chunk_size
        for item in self.puts:
            if item["storage_key"] == storage_key:
                yield item["content"]
                return
        raise FileNotFoundError(storage_key)
