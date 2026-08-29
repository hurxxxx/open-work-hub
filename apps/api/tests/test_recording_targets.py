from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocPage
from open_work_hub_api.domains.recording import blob_store
from open_work_hub_api.domains.recording import service as recording_service
from open_work_hub_api.domains.recording.models import (
    Recording,
    RecordingPublication,
    RecordingResult,
)

from test_meeting import _auth_headers, _bootstrap_admin_session, _first_workspace_slug


class _FakeRecordingMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        del bucket, length, content_type
        self.objects[key] = data.read()

    def fput_object(self, bucket: str, key: str, file_path: str, content_type: str) -> None:
        del bucket, content_type
        self.objects[key] = Path(file_path).read_bytes()


def _install_fake_recording_storage(monkeypatch) -> _FakeRecordingMinio:
    fake = _FakeRecordingMinio()
    monkeypatch.setattr(blob_store, "get_minio_client", lambda: fake)
    monkeypatch.setattr(recording_service, "_broker_is_reachable", lambda: True)
    monkeypatch.setattr(
        recording_service,
        "new_recording_attempt_id",
        lambda recording_id: f"task-{recording_id}",
    )
    monkeypatch.setattr(
        recording_service,
        "enqueue_recording_pipeline",
        lambda recording_id, attempt_id: None,
    )
    return fake


def _create_meeting(client, token: str, *, workspace_slug: str, title: str) -> dict:
    start = datetime(2026, 5, 1, 10, 0, 0)
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "Discuss recording targets.",
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=1)).isoformat(),
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _import_recording(client, token: str, *, workspace_slug: str, title: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/import",
        headers=_auth_headers(token),
        data={"title": title, "source": "manual_upload"},
        files={"file": (f"{title}.wav", b"audio-bytes", "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _attach_meeting(client, token: str, *, workspace_slug: str, recording_id: str, meeting_id: str):
    return client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/{recording_id}/targets",
        headers=_auth_headers(token),
        json={
            "target_app": "meeting",
            "target_type": "meeting",
            "target_id": meeting_id,
        },
    )


def _complete_recording_result(recording_id: str, *, version: int = 1) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with get_session_factory()() as session:
        recording = session.get(Recording, recording_id)
        assert recording is not None
        recording.transcript_status = "done"
        recording.summary_status = "done"
        recording.progress_pct = 100
        session.add(
            RecordingResult(
                recording_id=recording.id,
                transcript_text="원문 전사 내용",
                summary_text="핵심 요약 내용",
                verifier_note="검증: 통과",
                version=version,
                generated_at=now,
            )
        )
        session.add(recording)
        session.commit()


def test_recording_result_requires_explicit_idempotent_docs_publication(
    client,
    monkeypatch,
) -> None:
    _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    recording = _import_recording(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        title="explicit publication",
    )
    detail_path = f"/api/v1/workspaces/{workspace_slug}/recording/recordings/{recording['id']}"
    publish_path = f"{detail_path}/publications/docs"

    with get_session_factory()() as session:
        docs_before = session.scalar(select(func.count()).select_from(NativeDoc))

    not_ready = client.post(publish_path, headers=_auth_headers(admin["token"]))
    assert not_ready.status_code == 409, not_ready.text
    assert not_ready.json()["code"] == "recording.result_not_ready"

    _complete_recording_result(recording["id"])
    detail = client.get(detail_path, headers=_auth_headers(admin["token"]))
    assert detail.status_code == 200, detail.text
    assert detail.json()["result"] == {
        "transcript_text": "원문 전사 내용",
        "summary_text": "핵심 요약 내용",
        "verifier_note": "검증: 통과",
        "version": 1,
        "generated_at": detail.json()["result"]["generated_at"],
        "updated_at": detail.json()["result"]["updated_at"],
    }
    assert detail.json()["publications"] == []

    listing = client.get(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings",
        headers=_auth_headers(admin["token"]),
    )
    assert listing.status_code == 200, listing.text
    listed = next(item for item in listing.json()["items"] if item["id"] == recording["id"])
    assert "result" not in listed
    assert "publications" not in listed

    first = client.post(publish_path, headers=_auth_headers(admin["token"]))
    second = client.post(publish_path, headers=_auth_headers(admin["token"]))
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["target_app"] == "docs"
    assert first.json()["result_version"] == 1

    with get_session_factory()() as session:
        assert session.scalar(select(func.count()).select_from(NativeDoc)) == docs_before + 1
        assert session.scalar(select(func.count()).select_from(RecordingPublication)) == 1
        doc = session.get(NativeDoc, first.json()["target_resource_id"])
        assert doc is not None
        assert doc.source_app == "recording"
        assert doc.source_kind == "recording_result"
        assert doc.source_ref == f"{recording['id']}:1"
        page = session.scalar(select(NativeDocPage).where(NativeDocPage.doc_id == doc.id))
        assert page is not None
        rendered_blocks = str(page.content_blocks)
        assert "핵심 요약 내용" in rendered_blocks
        assert "원문 전사 내용" in rendered_blocks

    after = client.get(detail_path, headers=_auth_headers(admin["token"]))
    assert after.status_code == 200, after.text
    assert [item["id"] for item in after.json()["publications"]] == [first.json()["id"]]


def test_recording_meeting_attach_assigns_sequence_and_is_idempotent(client, monkeypatch):
    _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    meeting = _create_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        title="Recording attach target",
    )
    first = _import_recording(client, admin["token"], workspace_slug=workspace_slug, title="first")
    second = _import_recording(
        client, admin["token"], workspace_slug=workspace_slug, title="second"
    )

    first_attach = _attach_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        recording_id=first["id"],
        meeting_id=meeting["id"],
    )
    first_again = _attach_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        recording_id=first["id"],
        meeting_id=meeting["id"],
    )
    second_attach = _attach_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        recording_id=second["id"],
        meeting_id=meeting["id"],
    )

    assert first_attach.status_code == 200, first_attach.text
    assert first_again.status_code == 200, first_again.text
    assert second_attach.status_code == 200, second_attach.text

    first_meeting_links = [
        item
        for item in first_again.json()["targets"]
        if item["target_app"] == "meeting" and item["target_id"] == meeting["id"]
    ]
    assert len(first_meeting_links) == 1
    assert first_meeting_links[0]["target_title"] == "Recording attach target"
    assert first_meeting_links[0]["sort_order"] == 1

    detail = client.get(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert [item["sequence_no"] for item in detail.json()["recordings"]] == [1, 2]


def test_import_recording_can_attach_initial_meeting_target(client, monkeypatch):
    _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    meeting = _create_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        title="Initial import target",
    )

    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/import",
        headers=_auth_headers(admin["token"]),
        data={
            "title": "field recording",
            "source": "manual_upload",
            "initial_target_app": "meeting",
            "initial_target_type": "meeting",
            "initial_target_id": meeting["id"],
        },
        files={"file": ("field.wav", b"audio-bytes", "audio/wav")},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    meeting_links = [
        item
        for item in body["targets"]
        if item["target_app"] == "meeting" and item["target_id"] == meeting["id"]
    ]
    assert len(meeting_links) == 1
    assert meeting_links[0]["target_title"] == "Initial import target"
    assert meeting_links[0]["sort_order"] == 1

    detail = client.get(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert [item["id"] for item in detail.json()["recordings"]] == [body["id"]]


def test_recording_staging_accepts_tus_offset_upload(client, monkeypatch):
    fake = _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    auth_headers = _auth_headers(admin["token"])

    init = client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging",
        headers=auth_headers,
        json={
            "idempotency_key": "tus-offset-test",
            "mime_type": "audio/webm",
            "title": "Tus upload",
        },
    )
    assert init.status_code == 201, init.text
    staging_id = init.json()["id"]

    head = client.head(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging/{staging_id}/tus",
        headers={**auth_headers, "Tus-Resumable": "1.0.0"},
    )
    assert head.status_code == 204, head.text
    assert head.headers["Upload-Offset"] == "0"

    first = b"audio-"
    first_checksum = base64.b64encode(hashlib.sha256(first).digest()).decode("ascii")
    patch_first = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging/{staging_id}/tus",
        headers={
            **auth_headers,
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Upload-Checksum": f"sha256 {first_checksum}",
            "Content-Type": "application/offset+octet-stream",
        },
        content=first,
    )
    assert patch_first.status_code == 204, patch_first.text
    assert patch_first.headers["Upload-Offset"] == str(len(first))

    conflict = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging/{staging_id}/tus",
        headers={
            **auth_headers,
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
        },
        content=b"wrong-offset",
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.headers["Upload-Offset"] == str(len(first))

    second = b"bytes"
    patch_second = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging/{staging_id}/tus",
        headers={
            **auth_headers,
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": str(len(first)),
            "Content-Type": "application/offset+octet-stream",
        },
        content=second,
    )
    assert patch_second.status_code == 204, patch_second.text
    assert patch_second.headers["Upload-Offset"] == str(len(first) + len(second))

    complete = client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/staging/{staging_id}/complete",
        headers=auth_headers,
        json={
            "title": "Tus upload",
            "duration_sec_estimate": 2,
            "source": "quick_record",
        },
    )
    assert complete.status_code == 200, complete.text
    body = complete.json()
    assert body["file_size"] == len(first) + len(second)
    assert fake.objects[body["storage_key"]] == first + second


def test_recording_tus_creation_uses_upload_metadata(client, monkeypatch):
    _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])

    def metadata_value(value: str) -> str:
        return base64.b64encode(value.encode("utf-8")).decode("ascii")

    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/recording/recordings/tus",
        headers={
            **_auth_headers(admin["token"]),
            "Tus-Resumable": "1.0.0",
            "Upload-Metadata": (
                f"idempotency_key {metadata_value('tus-create-test')},"
                f"mime_type {metadata_value('audio/webm')},"
                f"title {metadata_value('Tus created')}"
            ),
        },
    )

    assert response.status_code == 201, response.text
    assert response.headers["Tus-Resumable"] == "1.0.0"
    assert response.headers["Upload-Offset"] == "0"
    assert "/recordings/staging/" in response.headers["Location"]
    assert response.headers["Location"].endswith("/tus")
