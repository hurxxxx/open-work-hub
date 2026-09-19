import json
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from conftest import complete, new_task, notify, plan
from starlette.requests import Request

from codex_console import store
from codex_console.errors import ConsoleError
from codex_console.models import Attachment


def upload(client, task, name="설계 문서.reference", content=b"original bytes", id=None):
    return client.put(
        f"/api/tasks/{task['id']}/attachments/{id or uuid4()}",
        content=content,
        headers={"content-type": "application/octet-stream", "x-file-name": quote(name)},
    )


def message(client, task, ids=(), text="Read my references", suffix="messages", operation_id=None):
    return client.post(
        f"/api/tasks/{task['id']}/{suffix}",
        json={
            "operation_id": operation_id or str(uuid4()),
            "text": text,
            "attachment_ids": list(ids),
        },
    )


def latest_input(client, method="turn/start"):
    return [p for m, p in client.app.state.runtime.rpc.calls if m == method][-1]


def manifest(params):
    return json.loads(params["input"][-1]["text"].split("\n", 1)[1])


def test_arbitrary_files_round_trip_and_duplicate_uploads(client, settings):
    task = new_task(client)
    content = bytes(range(256)) * 1025  # Exceeds the regular JSON request cap.
    id = str(uuid4())
    first = upload(client, task, "첨부.unknown", content, id)
    assert first.status_code == 200
    assert upload(client, task, "첨부.unknown", content, id).json() == first.json()
    assert upload(client, task, "첨부.unknown", b"different", id).status_code == 409
    other = upload(client, task, "첨부.unknown", b"second").json()
    assert other["id"] != first.json()["id"]
    result = client.get(f"/api/tasks/{task['id']}/attachments/{id}/download")
    assert result.content == content
    assert result.headers["content-type"] == "application/octet-stream"
    assert result.headers["content-disposition"].startswith("attachment;")
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["cache-control"] == "no-store"
    assert len(client.get(f"/api/tasks/{task['id']}/attachments").json()) == 2
    assert not settings.attachment_cache.exists()  # Uploading is not referencing.
    assert client.app.state.runtime.rpc is None


def test_only_selected_files_are_sent_and_cache_is_rebuildable(client, settings):
    task = new_task(client)
    first = upload(client, task, "A.anything", b"reference A").json()
    second = upload(client, task, "B.bin", b"reference B").json()
    task = message(client, task, [first["id"]], text="").json()
    params = latest_input(client)
    files = manifest(params)
    assert [f["name"] for f in files] == [first["name"]]
    path = Path(files[0]["path"])
    assert path.read_bytes() == b"reference A"
    assert not path.is_relative_to(settings.workspace)
    assert path.stat().st_mode & 0o777 == 0o400
    assert not (settings.attachment_cache / task["id"] / second["id"]).exists()
    assert "reference A" not in json.dumps(params)  # Content is read by Codex, not inlined.
    operation_id = params["clientUserMessageId"]
    notify(
        client,
        task,
        "item/completed",
        {
            "item": {
                "id": str(uuid4()),
                "clientId": operation_id,
                "type": "userMessage",
                "content": params["input"],
            }
        },
    )
    task = complete(client, task)
    item = next(i for i in task["items"] if i.get("clientId") == operation_id)
    assert item["content"] == [{"type": "text", "text": ""}]
    assert item["attachments"] == [first]
    path.unlink()
    task = message(client, task, text="Continue without new files").json()
    assert latest_input(client)["input"] == [{"type": "text", "text": "Continue without new files"}]
    assert path.read_bytes() == b"reference A"  # Older conversation references still resolve.
    complete(client, task)


def test_steer_and_implementation_use_explicit_selection(client):
    task = plan(client)
    first = upload(client, task, "first.data").json()
    second = upload(client, task, "second.data").json()
    response = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
            "attachment_ids": [first["id"]],
        },
    )
    assert response.status_code == 200
    assert [f["name"] for f in manifest(latest_input(client))] == ["first.data"]
    task = response.json()
    assert message(client, task, [second["id"]], suffix="steer").status_code == 200
    assert [f["name"] for f in manifest(latest_input(client, "turn/steer"))] == ["second.data"]
    assert message(client, task, suffix="steer").status_code == 200
    assert latest_input(client, "turn/steer")["input"] == [
        {"type": "text", "text": "Read my references"}
    ]
    complete(client, task)


def test_selection_is_task_scoped_and_part_of_idempotency(client):
    task, other = new_task(client), new_task(client)
    file = upload(client, task).json()
    assert message(client, other, [file["id"]]).status_code == 404
    assert message(client, task, [file["id"], file["id"]]).status_code == 422
    assert message(client, task, [], text="").status_code == 422
    id = str(uuid4())
    response = message(client, task, [file["id"]], operation_id=id)
    assert response.status_code == 200
    assert message(client, task, [file["id"]], operation_id=id).status_code == 200
    assert message(client, task, [], operation_id=id).status_code == 409
    assert len([m for m, _ in client.app.state.runtime.rpc.calls if m == "turn/start"]) == 1
    complete(client, response.json())


def test_delete_removes_bytes_preserves_message_badge_and_blocks_active_tasks(client, settings):
    task = new_task(client)
    file = upload(client, task).json()
    task = message(client, task, [file["id"]]).json()
    params = latest_input(client)
    path = Path(manifest(params)[0]["path"])
    notify(
        client,
        task,
        "item/completed",
        {
            "item": {
                "id": str(uuid4()),
                "clientId": params["clientUserMessageId"],
                "type": "userMessage",
                "content": params["input"],
            }
        },
    )
    endpoint = f"/api/tasks/{task['id']}/attachments/{file['id']}"
    assert client.delete(endpoint).status_code == 409
    complete(client, task)
    assert client.delete(endpoint).status_code == 200
    assert not path.exists()
    assert client.get(endpoint + "/download").status_code == 404
    assert message(client, task, [file["id"]]).status_code == 404
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["attachments"] == []
    item = next(i for i in detail["items"] if i["type"] == "userMessage")
    assert item["attachments"][0]["deleted"] is True
    with client.app.state.factory() as db:
        assert db.get(Attachment, file["id"]).content is None


@pytest.mark.parametrize("name", ["../file", "a/b", "a\\b", ".", "..", "bad\nname", "x" * 256])
def test_path_and_header_injection_are_rejected(client, name):
    assert upload(client, new_task(client), name).status_code == 422


def test_upload_caps_apply_to_streamed_bytes_and_quota(client, settings):
    task = new_task(client)
    settings.attachment_max_bytes = 8
    settings.attachment_task_max_bytes = 10
    assert upload(client, task, content=b"123456789").status_code == 413
    assert upload(client, task, content=iter([b"1234", b"56789"])).status_code == 413
    assert upload(client, task, content=b"123456").status_code == 200
    assert upload(client, task, content=b"12345").status_code == 413
    assert len(client.get(f"/api/tasks/{task['id']}/attachments").json()) == 1


def test_disconnected_stream_never_persists_partial_content(client):
    task = new_task(client)
    events = iter(
        [
            {"type": "http.request", "body": b"partial bytes", "more_body": True},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(events)

    request = Request(
        {
            "type": "http",
            "app": client.app,
            "headers": [(b"content-type", b"application/octet-stream")],
        },
        receive,
    )
    endpoint = next(
        route.endpoint
        for route in client.app.routes
        if getattr(route, "name", "") == "upload_attachment"
    )
    with pytest.raises(ConsoleError, match="attachment_upload_cancelled"):
        client.portal.call(endpoint, UUID(task["id"]), uuid4(), request, "partial.data")
    assert client.get(f"/api/tasks/{task['id']}/attachments").json() == []


def test_authentication_and_csrf_protect_upload_download_and_delete(client):
    task = new_task(client)
    file = upload(client, task).json()
    endpoint = f"/api/tasks/{task['id']}/attachments/{file['id']}"
    assert (
        client.put(endpoint, content=b"secret", headers={"x-csrf-token": "bad"}).status_code == 401
    )
    assert client.delete(endpoint, headers={"origin": "https://evil.invalid"}).status_code == 403
    other = new_task(client)
    assert (
        client.get(f"/api/tasks/{other['id']}/attachments/{file['id']}/download").status_code == 404
    )
    client.delete("/api/session")
    assert client.get(endpoint + "/download").status_code == 401
    assert client.put(endpoint, content=b"secret").status_code == 401
    assert client.delete(endpoint).status_code == 401


def test_symlink_cache_is_rejected_without_touching_target(client, settings, tmp_path):
    task = new_task(client)
    file = upload(client, task).json()
    target = tmp_path / "target"
    target.mkdir()
    settings.attachment_cache.symlink_to(target, target_is_directory=True)
    response = message(client, task, [file["id"]])
    assert response.status_code == 503
    assert not list(target.iterdir())


def test_native_history_reconciliation_keeps_attachment_metadata(client):
    task = new_task(client)
    file = upload(client, task).json()
    task = message(client, task, [file["id"]]).json()
    params = latest_input(client)
    with client.app.state.factory.begin() as db:
        row = store.require_task(db, task["id"])
        store.reconcile_history(
            db,
            row,
            [
                {
                    "id": task["turn_id"],
                    "items": [
                        {
                            "id": str(uuid4()),
                            "clientId": params["clientUserMessageId"],
                            "type": "userMessage",
                            "content": params["input"],
                        }
                    ],
                }
            ],
        )
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["items"][0]["attachments"] == [file]
    complete(client, task)
