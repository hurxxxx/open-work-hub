from __future__ import annotations

from ai_do_api.domains.recording import service as recording_service

from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting


class _FakeRecordingMinio:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, bucket: str, key: str, data, length: int, content_type: str) -> None:
        del bucket, length, content_type
        self.objects[key] = data.read()


def _install_fake_recording_storage(monkeypatch) -> _FakeRecordingMinio:
    fake = _FakeRecordingMinio()
    monkeypatch.setattr(recording_service, "get_minio_client", lambda: fake)
    monkeypatch.setattr(recording_service, "_broker_is_reachable", lambda: True)
    monkeypatch.setattr(
        recording_service,
        "enqueue_recording_pipeline",
        lambda recording_id: f"task-{recording_id}",
    )
    return fake


def _import_recording(client, token: str, *, title: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/recording/recordings/import",
        headers=_auth_headers(token),
        data={"title": title, "source": "manual_upload"},
        files={"file": (f"{title}.wav", b"audio-bytes", "audio/wav")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _attach_meeting(client, token: str, *, recording_id: str, meeting_id: str):
    return client.post(
        f"/api/v1/workspaces/hq/recording/recordings/{recording_id}/containers",
        headers=_auth_headers(token),
        json={
            "container_app": "meeting",
            "container_type": "meeting",
            "container_id": meeting_id,
        },
    )


def test_recording_meeting_attach_assigns_sequence_and_is_idempotent(client, monkeypatch):
    _install_fake_recording_storage(monkeypatch)
    admin = _bootstrap_admin_session(client)
    meeting = _create_meeting(client, admin["token"], title="Recording attach target")
    first = _import_recording(client, admin["token"], title="first")
    second = _import_recording(client, admin["token"], title="second")

    first_attach = _attach_meeting(
        client,
        admin["token"],
        recording_id=first["id"],
        meeting_id=meeting["id"],
    )
    first_again = _attach_meeting(
        client,
        admin["token"],
        recording_id=first["id"],
        meeting_id=meeting["id"],
    )
    second_attach = _attach_meeting(
        client,
        admin["token"],
        recording_id=second["id"],
        meeting_id=meeting["id"],
    )

    assert first_attach.status_code == 200, first_attach.text
    assert first_again.status_code == 200, first_again.text
    assert second_attach.status_code == 200, second_attach.text

    first_meeting_links = [
        item
        for item in first_again.json()["containers"]
        if item["container_app"] == "meeting" and item["container_id"] == meeting["id"]
    ]
    assert len(first_meeting_links) == 1
    assert first_meeting_links[0]["container_title"] == "Recording attach target"
    assert first_meeting_links[0]["sort_order"] == 1

    detail = client.get(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert [item["sequence_no"] for item in detail.json()["recordings"]] == [1, 2]
