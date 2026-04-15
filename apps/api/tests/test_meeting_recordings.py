from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from aidoo_api.core.db import get_engine
from aidoo_api.domains.meeting.models import MeetingRecording, MeetingRecordingStaging
from aidoo_api.domains.meeting import recordings as recording_service

from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting


class _FakeRecordingMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        del bucket, length, content_type
        self.objects[key] = data.read()

    def fput_object(self, bucket: str, key: str, path: str, content_type: str | None = None) -> None:
        del bucket, content_type
        self.objects[key] = Path(path).read_bytes()

    def fget_object(self, bucket: str, key: str, path: str) -> None:
        del bucket
        Path(path).write_bytes(self.objects[key])

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
    monkeypatch.setattr(recording_service, "get_minio_client", lambda: fake)
    monkeypatch.setattr(recording_service, "_recording_spool_root", lambda: spool_root)
    monkeypatch.setattr(recording_service, "_broker_is_reachable", lambda: True)
    monkeypatch.setattr(recording_service, "enqueue_recording_pipeline", lambda recording_id: f"task-{recording_id}")
    return fake


def test_init_staging_is_idempotent(client, monkeypatch, tmp_path) -> None:
    _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording init")

    payload = {"idempotency_key": "rec-init-1", "mime_type": "audio/webm"}
    first = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json=payload,
    )
    second = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json=payload,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]

    with Session(get_engine()) as session:
        rows = session.query(MeetingRecordingStaging).all()
        assert len(rows) == 1


def test_chunk_upload_same_seq_same_payload_is_idempotent(client, monkeypatch, tmp_path) -> None:
    _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording chunk")
    init_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json={"idempotency_key": "rec-chunk-1", "mime_type": "audio/webm"},
    )
    staging_id = init_response.json()["id"]
    chunk = b"hello recording chunk"
    digest = hashlib.sha256(chunk).hexdigest()

    first = client.put(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )
    second = client.put(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["bytes_received"] == len(chunk)
    assert second.json()["bytes_received"] == len(chunk)

    with Session(get_engine()) as session:
        staging = session.get(MeetingRecordingStaging, staging_id)
        assert staging is not None
        assert staging.chunk_count == 1
        assert staging.bytes_received == len(chunk)


def test_complete_staging_promotes_to_recording(client, monkeypatch, tmp_path) -> None:
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording complete")
    init_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json={"idempotency_key": "rec-complete-1", "mime_type": "audio/webm"},
    )
    staging_id = init_response.json()["id"]
    chunk = b"final recording chunk"
    digest = hashlib.sha256(chunk).hexdigest()
    upload_response = client.put(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )
    assert upload_response.status_code == 200, upload_response.text

    complete_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/complete",
        headers=_auth_headers(admin["token"]),
        json={"duration_sec_estimate": 4},
    )
    assert complete_response.status_code == 200, complete_response.text
    body = complete_response.json()
    assert len(body["recordings"]) == 1
    assert body["recordings"][0]["source"] == "live_recording"
    assert body["recordings"][0]["progress_pct"] == 10

    with Session(get_engine()) as session:
        recording = session.get(MeetingRecording, staging_id)
        assert recording is not None
        assert recording.celery_task_id == f"task-{staging_id}"
        assert fake_minio.objects[recording.storage_key] == chunk


def test_failed_recording_still_allows_playback(client, monkeypatch, tmp_path) -> None:
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Failed playback")

    with Session(get_engine()) as session:
        recording = MeetingRecording(
            id="rec-failed-1",
            meeting_id=meeting["id"],
            storage_key="meeting-recordings/demo/rec-failed-1/recording.webm",
            duration_sec=5,
            file_size=5,
            mime_type="audio/webm",
            idempotency_key="failed-playback",
            uploaded_by_id=admin["user"]["id"],
            source="manual_upload",
            transcription_status="failed",
            progress_pct=70,
            failure_reason="summary failed",
        )
        session.add(recording)
        session.commit()
        fake_minio.objects[recording.storage_key] = b"abcde"

    playback = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/rec-failed-1/playback",
        headers=_auth_headers(admin["token"]),
    )
    assert playback.status_code == 200, playback.text
    assert playback.json()["url"].startswith("https://fake-minio.local/")


def test_import_recording_keeps_raw_audio_when_enqueue_fails(client, monkeypatch, tmp_path) -> None:
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(
        recording_service,
        "enqueue_recording_pipeline",
        lambda recording_id: (_ for _ in ()).throw(RuntimeError(f"queue down for {recording_id}")),
    )
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording import enqueue failure")

    response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/import",
        headers=_auth_headers(admin["token"]),
        files={"file": ("recording.wav", b"imported-audio", "audio/wav")},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["recordings"]) == 1
    assert body["recordings"][0]["source"] == "manual_upload"
    assert body["recordings"][0]["transcription_status"] == "failed"
    assert "Raw audio was saved" in body["recordings"][0]["failure_reason"]

    with Session(get_engine()) as session:
        recording = session.get(MeetingRecording, body["recordings"][0]["id"])
        assert recording is not None
        assert recording.celery_task_id is None
        assert recording.transcription_status == "failed"
        assert fake_minio.objects[recording.storage_key] == b"imported-audio"


def test_complete_staging_keeps_recording_when_enqueue_fails(client, monkeypatch, tmp_path) -> None:
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    monkeypatch.setattr(
        recording_service,
        "enqueue_recording_pipeline",
        lambda recording_id: (_ for _ in ()).throw(RuntimeError(f"queue down for {recording_id}")),
    )
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording complete enqueue failure")
    init_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin["token"]),
        json={"idempotency_key": "rec-complete-fail-1", "mime_type": "audio/webm"},
    )
    staging_id = init_response.json()["id"]
    chunk = b"final recording chunk"
    digest = hashlib.sha256(chunk).hexdigest()

    upload_response = client.put(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin["token"]), "X-Chunk-Sha256": digest},
        files={"file": ("chunk-0.webm", chunk, "audio/webm")},
    )
    assert upload_response.status_code == 200, upload_response.text

    complete_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/complete",
        headers=_auth_headers(admin["token"]),
        json={"duration_sec_estimate": 4},
    )

    assert complete_response.status_code == 200, complete_response.text
    body = complete_response.json()
    assert len(body["recordings"]) == 1
    assert body["recordings"][0]["transcription_status"] == "failed"
    assert "Raw audio was saved" in body["recordings"][0]["failure_reason"]

    with Session(get_engine()) as session:
        recording = session.get(MeetingRecording, staging_id)
        assert recording is not None
        assert recording.celery_task_id is None
        assert recording.transcription_status == "failed"
        assert fake_minio.objects[recording.storage_key] == chunk


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
        email="second-recorder@aidoo.local",
        full_name="Second Recorder",
        workspace_keys=["meeting"],
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
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "lock-test-admin", "mime_type": "audio/webm"},
    )
    assert first_init.status_code == 201, first_init.text
    admin_staging_id = first_init.json()["id"]

    # Second user tries to start a recording while admin is still active → 409.
    blocked = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "lock-test-second", "mime_type": "audio/webm"},
    )
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "recording_in_progress"
    assert detail["active_recorder_id"] == admin["user"]["id"]
    assert detail["active_recorder_name"] == admin["user"]["full_name"]
    assert detail["active_staging_id"] == admin_staging_id

    # Admin can still resume their own staging (idempotent path).
    same_admin = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "lock-test-admin", "mime_type": "audio/webm"},
    )
    assert same_admin.status_code == 201
    assert same_admin.json()["id"] == admin_staging_id

    # The meeting detail exposes the active recorder so the frontend can disable
    # the start button on other users' UIs.
    detail_response = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
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
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{admin_staging_id}/chunks/0",
        headers={**_auth_headers(admin_token), "X-Chunk-Sha256": digest},
        files={"file": ("0.webm", chunk, "audio/webm")},
    )
    assert upload.status_code == 200, upload.text
    complete = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{admin_staging_id}/complete",
        headers=_auth_headers(admin_token),
        json={"duration_sec_estimate": 1},
    )
    assert complete.status_code == 200

    # Second user can now start.
    after_release = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "lock-test-second", "mime_type": "audio/webm"},
    )
    assert after_release.status_code == 201, after_release.text


def test_delete_recording_permission_and_cleanup(client, monkeypatch, tmp_path) -> None:
    """Recording delete: organizer or uploader can remove a finalized recording.
    Other participants get 403, the minio object is removed, and the row is gone."""
    fake_minio = _install_fake_recording_storage(monkeypatch, tmp_path)
    from test_meeting import _create_user_with_workspaces, _login

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    other = _create_user_with_workspaces(
        client,
        admin_token,
        email="other-recording@aidoo.local",
        full_name="Other Recording",
        workspace_keys=["meeting"],
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
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "delete-test", "mime_type": "audio/webm"},
    )
    assert init.status_code == 201
    staging_id = init.json()["id"]
    chunk = b"y"
    digest = hashlib.sha256(chunk).hexdigest()
    upload = client.put(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/chunks/0",
        headers={**_auth_headers(admin_token), "X-Chunk-Sha256": digest},
        files={"file": ("0.webm", chunk, "audio/webm")},
    )
    assert upload.status_code == 200, upload.text
    complete = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging/{staging_id}/complete",
        headers=_auth_headers(admin_token),
        json={"duration_sec_estimate": 1},
    )
    assert complete.status_code == 200
    body = complete.json()
    assert len(body["recordings"]) == 1
    recording_id = body["recordings"][0]["id"]
    storage_key = body["recordings"][0]["storage_key"] if "storage_key" in body["recordings"][0] else None

    # Capture the storage key directly from the DB so we can verify minio removal.
    with Session(get_engine()) as session:
        row = session.get(MeetingRecording, recording_id)
        assert row is not None
        storage_key = row.storage_key
    assert storage_key in fake_minio.objects

    # Non-uploader / non-organizer attendee cannot delete.
    forbidden = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/{recording_id}",
        headers=_auth_headers(other_token),
    )
    assert forbidden.status_code == 403

    # Admin (also the uploader here) deletes successfully.
    deleted = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/{recording_id}",
        headers=_auth_headers(admin_token),
    )
    assert deleted.status_code == 200, deleted.text
    after_body = deleted.json()
    assert after_body["recordings"] == []

    with Session(get_engine()) as session:
        assert session.get(MeetingRecording, recording_id) is None

    # Minio object was removed.
    assert storage_key not in fake_minio.objects
    assert storage_key in fake_minio.removed


def test_stale_recording_lock_auto_releases(client, monkeypatch, tmp_path) -> None:
    """If the recorder crashes (no chunk for > RECORDING_STALE_AFTER_SECONDS),
    the lock auto-releases so other participants are not permanently blocked.
    The abandoned staging row stays in the DB but is excluded from the active
    lock calculation."""
    from datetime import timedelta

    _install_fake_recording_storage(monkeypatch, tmp_path)
    from test_meeting import _create_user_with_workspaces, _login

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    second = _create_user_with_workspaces(
        client,
        admin_token,
        email="stale-second@aidoo.local",
        full_name="Stale Second",
        workspace_keys=["meeting"],
    )
    second_token = _login(client, second["user"]["email"], second["temporary_password"])

    meeting = _create_meeting(
        client,
        admin_token,
        title="Stale lock test",
        attendees=[{"user_id": second["user"]["id"], "role": "required"}],
    )

    # Admin starts a recording and then "crashes" (we simulate by aging the
    # last_chunk_at back past the stale window).
    init = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(admin_token),
        json={"idempotency_key": "stale-test-admin", "mime_type": "audio/webm"},
    )
    assert init.status_code == 201
    admin_staging_id = init.json()["id"]

    # While the lock is fresh, second user is blocked.
    blocked = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "stale-test-second-1", "mime_type": "audio/webm"},
    )
    assert blocked.status_code == 409

    # Simulate a crash: bump last_chunk_at back 5 minutes.
    with Session(get_engine()) as session:
        staging = session.get(MeetingRecordingStaging, admin_staging_id)
        assert staging is not None
        staging.last_chunk_at = staging.last_chunk_at - timedelta(minutes=5)
        session.commit()

    # Now the meeting detail should report no active lock.
    detail = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(second_token),
    )
    assert detail.status_code == 200
    assert detail.json()["active_recording_lock"] is None

    # And the second user can start their own recording.
    take_over = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/recordings/staging",
        headers=_auth_headers(second_token),
        json={"idempotency_key": "stale-test-second-2", "mime_type": "audio/webm"},
    )
    assert take_over.status_code == 201, take_over.text
    second_staging_id = take_over.json()["id"]
    assert second_staging_id != admin_staging_id

    # The abandoned admin staging row is still in the DB (just no longer locking).
    with Session(get_engine()) as session:
        rows = (
            session.query(MeetingRecordingStaging)
            .filter(MeetingRecordingStaging.meeting_id == meeting["id"])
            .all()
        )
        assert len(rows) == 2
        admin_row = next(r for r in rows if r.id == admin_staging_id)
        assert admin_row.completed_at is None  # still "incomplete" — just stale
