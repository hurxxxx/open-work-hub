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
