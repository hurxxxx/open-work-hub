from __future__ import annotations

import hashlib
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_engine
from open_work_hub_api.domains.recording import blob_store
from open_work_hub_api.domains.recording import service as canonical_recording_service
from open_work_hub_api.domains.recording.models import Recording, RecordingTarget, RecordingStaging

from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting


class _FakeMinioObject:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def stream(self, chunk_size: int):
        for offset in range(0, len(self._data), chunk_size):
            yield self._data[offset : offset + chunk_size]

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class _FakeRecordingMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        del bucket, length, content_type
        self.objects[key] = data.read()

    def fput_object(
        self, bucket: str, key: str, path: str, content_type: str | None = None
    ) -> None:
        del bucket, content_type
        self.objects[key] = Path(path).read_bytes()

    def fget_object(self, bucket: str, key: str, path: str) -> None:
        del bucket
        Path(path).write_bytes(self.objects[key])

    def get_object(self, bucket: str, key: str) -> _FakeMinioObject:
        del bucket
        return _FakeMinioObject(self.objects[key])

    def remove_object(self, bucket: str, key: str) -> None:
        del bucket
        self.removed.append(key)
        self.objects.pop(key, None)

    def presigned_get_object(self, bucket: str, key: str, expires) -> str:
        del bucket, expires
        return f"https://fake-minio.local/{key}"


def _install_fake_recording_storage(monkeypatch, tmp_path) -> _FakeRecordingMinio:
    fake = _FakeRecordingMinio()
    spool_root = tmp_path / "recording-spool"
    spool_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(blob_store, "get_minio_client", lambda: fake)
    monkeypatch.setattr(blob_store, "recording_spool_root", lambda: spool_root)
    monkeypatch.setattr(canonical_recording_service, "_broker_is_reachable", lambda: True)
    monkeypatch.setattr(
        canonical_recording_service,
        "new_recording_attempt_id",
        lambda recording_id: f"task-{recording_id}",
    )
    monkeypatch.setattr(
        canonical_recording_service,
        "enqueue_recording_pipeline",
        lambda recording_id, attempt_id: None,
    )
    return fake


def _meeting_recording_target(
    session: Session,
    *,
    meeting_id: str,
    recording_id: str,
) -> RecordingTarget:
    target = session.scalar(
        select(RecordingTarget).where(
            RecordingTarget.recording_id == recording_id,
            RecordingTarget.target_app == "meeting",
            RecordingTarget.target_type == "meeting",
            RecordingTarget.target_id == meeting_id,
        )
    )
    assert target is not None
    return target


def _meeting_staging_rows(session: Session, meeting_id: str) -> list[RecordingStaging]:
    return list(
        session.scalars(
            select(RecordingStaging).where(
                RecordingStaging.initial_target_app == "meeting",
                RecordingStaging.initial_target_type == "meeting",
                RecordingStaging.initial_target_id == meeting_id,
            )
        )
    )


def test_init_staging_is_idempotent(client, monkeypatch, tmp_path) -> None:
    _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording init")

    payload = {"idempotency_key": "rec-init-1", "mime_type": "audio/webm"}
    first = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json=payload,
    )
    second = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json=payload,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    with Session(get_engine()) as session:
        rows = _meeting_staging_rows(session, meeting["id"])
        assert len(rows) == 1


def test_chunk_upload_same_seq_same_payload_is_idempotent(client, monkeypatch, tmp_path) -> None:
    _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording chunk")
    init_response = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json={"idempotency_key": "rec-chunk-1", "mime_type": "audio/webm"},
    )
    staging_id = init_response.json()["id"]
    chunk = b"hello recording chunk"
    digest = hashlib.sha256(chunk).hexdigest()

    first = client.put(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )
    second = client.put(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["bytes_received"] == len(chunk)
    assert second.json()["bytes_received"] == len(chunk)

    with Session(get_engine()) as session:
        staging = session.get(RecordingStaging, staging_id)
        assert staging is not None
        assert staging.chunk_count == 1
        assert staging.bytes_received == len(chunk)


def test_complete_staging_promotes_to_recording(client, monkeypatch, tmp_path) -> None:
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording complete")
    init_response = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json={"idempotency_key": "rec-complete-1", "mime_type": "audio/webm"},
    )
    staging_id = init_response.json()["id"]
    chunk = b"final recording chunk"
    digest = hashlib.sha256(chunk).hexdigest()
    upload_response = client.put(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )
    assert upload_response.status_code == 200, upload_response.text

    complete_response = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/complete",
        headers=_auth_headers(admin["token"]),
        json={"duration_sec_estimate": 4},
    )
    assert complete_response.status_code == 200, complete_response.text
    body = complete_response.json()
    assert len(body["recordings"]) == 1
    assert body["recordings"][0]["source"] == "live_recording"
    assert body["recordings"][0]["progress_pct"] == 0

    with Session(get_engine()) as session:
        recording = session.get(Recording, staging_id)
        assert recording is not None
        assert recording.celery_task_id == f"task-{staging_id}"
        assert (
            _meeting_recording_target(
                session,
                meeting_id=meeting["id"],
                recording_id=recording.id,
            ).sort_order
            == 1
        )
        assert fake_minio.objects[recording.storage_key] == chunk
        assert re.fullmatch(
            rf"\d{{8}}T\d{{6}}Z-{recording.id}\.webm",
            Path(recording.storage_key).name,
        )


def test_only_one_user_can_record_at_a_time(client, monkeypatch, tmp_path) -> None:
    """Single-recorder lock: while one participant is staging an active
    recording, other participants get a 409 with the active recorder name."""
    _install_fake_recording_storage(monkeypatch, tmp_path)
    from test_meeting import (
        _create_user_with_workspaces,
        _login,
    )

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    second = _create_user_with_workspaces(
        client,
        admin_token,
        email="second-recorder@open-work-hub.local",
        full_name="Second Recorder",
        workspace_keys=["administrator"],
    )
    second_token = _login(client, second["user"]["email"], second["temporary_password"])

    meeting = _create_meeting(
        client,
        admin_token,
        title="Single recorder lock",
        attendees=[{"user_id": second["user"]["id"], "role": "required"}],
    )

    # Admin starts a recording.
    first_init = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "lock-test-admin", "mime_type": "audio/webm"},
    )
    assert first_init.status_code == 201, first_init.text
    admin_staging_id = first_init.json()["id"]

    # Second user tries to start a recording while admin is still active → 409.
    blocked = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "lock-test-second", "mime_type": "audio/webm"},
    )
    assert blocked.status_code == 409, blocked.text
    body = blocked.json()
    assert body["code"] == "meeting.recording_in_progress"
    assert body["params"]["active_recorder_id"] == admin["user"]["id"]
    assert body["params"]["active_recorder_name"] == admin["user"]["full_name"]
    assert body["params"]["active_staging_id"] == admin_staging_id

    # Admin can still resume their own staging (idempotent path).
    same_admin = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "lock-test-admin", "mime_type": "audio/webm"},
    )
    assert same_admin.status_code == 201
    assert same_admin.json()["id"] == admin_staging_id

    # The meeting detail exposes the active recorder so the frontend can disable
    # the start button on other users' UIs.
    detail_response = client.get(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(second_token),
    )
    assert detail_response.status_code == 200
    body = detail_response.json()
    lock = body["active_recording_lock"]
    assert lock is not None
    assert lock["user_id"] == admin["user"]["id"]
    assert lock["user_name"] == admin["user"]["full_name"]
    assert lock["staging_id"] == admin_staging_id

    # Admin uploads a chunk and completes — releases the lock.
    chunk = b"x"
    digest = hashlib.sha256(chunk).hexdigest()
    upload = client.put(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{admin_staging_id}/chunks/0",
        headers={**_auth_headers(admin_token), "X-Chunk-Sha256": digest},
        files={"file": ("0.webm", chunk, "audio/webm")},
    )
    assert upload.status_code == 200, upload.text
    complete = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{admin_staging_id}/complete",
        headers=_auth_headers(admin_token),
        json={"duration_sec_estimate": 1},
    )
    assert complete.status_code == 200

    # Second user can now start.
    after_release = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "lock-test-second", "mime_type": "audio/webm"},
    )
    assert after_release.status_code == 201, after_release.text


def test_delete_recording_permission_and_cleanup(client, monkeypatch, tmp_path) -> None:
    """Recording delete: organizer or uploader can archive a finalized recording.
    Other participants get 403, the recording disappears from the meeting, and
    raw audio stays available for retention cleanup."""
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    from test_meeting import _create_user_with_workspaces, _login

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    other = _create_user_with_workspaces(
        client,
        admin_token,
        email="other-recording@open-work-hub.local",
        full_name="Other Recording",
        workspace_keys=["administrator"],
    )
    other_token = _login(client, other["user"]["email"], other["temporary_password"])

    meeting = _create_meeting(
        client,
        admin_token,
        title="Delete recording test",
        attendees=[{"user_id": other["user"]["id"], "role": "required"}],
    )

    # Admin uploads + finalizes a recording.
    init = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "delete-test", "mime_type": "audio/webm"},
    )
    assert init.status_code == 201
    staging_id = init.json()["id"]
    chunk = b"y"
    digest = hashlib.sha256(chunk).hexdigest()
    upload = client.put(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin_token), "X-Chunk-Sha256": digest},
        files={"file": ("0.webm", chunk, "audio/webm")},
    )
    assert upload.status_code == 200, upload.text
    complete = client.post(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/complete",
        headers=_auth_headers(admin_token),
        json={"duration_sec_estimate": 1},
    )
    assert complete.status_code == 200
    body = complete.json()
    assert len(body["recordings"]) == 1
    recording_id = body["recordings"][0]["id"]
    storage_key = (
        body["recordings"][0]["storage_key"] if "storage_key" in body["recordings"][0] else None
    )

    # Capture the storage key directly from the DB so we can verify minio removal.
    with Session(get_engine()) as session:
        row = session.get(Recording, recording_id)
        assert row is not None
        storage_key = row.storage_key
    assert storage_key in fake_minio.objects

    # Non-uploader / non-organizer attendee cannot delete.
    forbidden = client.delete(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/{recording_id}",
        headers=_auth_headers(other_token),
    )
    assert forbidden.status_code == 403

    # Admin (also the uploader here) deletes successfully.
    deleted = client.delete(
        f"/api/v1/workspaces/administrator/meeting/meetings/{meeting['id']}/recordings/{recording_id}",
        headers=_auth_headers(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    after_body = deleted.json()
    assert after_body["recordings"] == []

    with Session(get_engine()) as session:
        row = session.get(Recording, recording_id)
        assert row is not None
        assert row.trashed_at is not None

    # Canonical recording delete archives the row and keeps raw audio available
    # for retention/cleanup rather than deleting the MinIO object inline.
    assert storage_key in fake_minio.objects
