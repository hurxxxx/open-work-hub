"""Opt-in native subscription/file-read check using a disposable database and checkout."""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import make_url

from codex_console.app import create_app
from codex_console.auth import CSRF_COOKIE, password_hash
from codex_console.cli import migrate
from codex_console.config import Settings
from codex_console.models import Owner, database


def main():
    url = make_url(os.environ["OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN"])
    name = "console_test_attachment_" + uuid4().hex
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            target = url.set(drivername="postgresql+psycopg", database=name).render_as_string(
                hide_password=False
            )
            migrate(target)
            engine, factory = database(target)
            password = str(uuid4())
            with factory.begin() as db:
                db.add(Owner(password_hash=password_hash(password)))
            engine.dispose()
            with tempfile.TemporaryDirectory(prefix="console-attachment-smoke-") as directory:
                root = Path(directory) / "dev"
                subprocess.run(
                    ["git", "init", "-b", "dev", str(root)], check=True, capture_output=True
                )
                settings = Settings(
                    database_url=target,
                    origin="http://localhost",
                    workspace=root,
                    attachment_cache=Path(directory) / "attachments",
                    web_dist=root / "absent",
                    _env_file=None,
                )
                with TestClient(create_app(settings), base_url="http://localhost") as client:
                    client.headers["origin"] = settings.origin
                    assert (
                        client.post("/api/session", json={"password": password}).status_code == 200
                    )
                    client.headers["x-csrf-token"] = client.cookies[CSRF_COOKIE]
                    assert client.get("/api/codex/account").json().get("auth_type") == "chatgpt"
                    task = client.post("/api/tasks", json={"title": "Attachment acceptance"}).json()
                    endpoint = f"/api/tasks/{task['id']}"
                    selected_id, unused_id, operation_id = (str(uuid4()) for _ in range(3))
                    marker = uuid4().hex
                    for id, filename, content in (
                        (selected_id, "design.reference", f"acceptance_word: {marker}\n".encode()),
                        (unused_id, "unused.bin", b"not selected"),
                    ):
                        assert (
                            client.put(
                                endpoint + "/attachments/" + id,
                                content=content,
                                headers={
                                    "content-type": "application/octet-stream",
                                    "x-file-name": filename,
                                },
                            ).status_code
                            == 200
                        )
                    assert not settings.attachment_cache.exists()
                    try:
                        result = client.post(
                            endpoint + "/messages",
                            json={
                                "operation_id": operation_id,
                                "text": (
                                    "Read the attached reference file with a tool and report its "
                                    "exact acceptance_word value in your final summary. "
                                    "This is a read-only attachment check; no changes or follow-up "
                                    "questions are needed."
                                ),
                                "attachment_ids": [selected_id],
                            },
                        )
                        assert result.status_code == 200, result.json().get("code")
                        deadline = time.monotonic() + 240
                        while time.monotonic() < deadline:
                            task = client.get(endpoint).json()
                            if task["requests"]:
                                raise RuntimeError(
                                    "Unexpected interactive request in read-only smoke"
                                )
                            if task["status"] not in ("starting", "running", "waiting"):
                                break
                            time.sleep(1)
                        assert task["status"] == "idle", task["error_code"] or task["status"]
                        assert any(
                            marker in item.get("text", "")
                            for item in task["items"]
                            if item["type"] in ("agentMessage", "plan")
                        )
                        user = next(
                            item for item in task["items"] if item.get("clientId") == operation_id
                        )
                        assert [file["id"] for file in user["attachments"]] == [selected_id]
                        assert not (settings.attachment_cache / task["id"] / unused_id).exists()
                        assert not subprocess.check_output(
                            ["git", "-C", str(root), "status", "--porcelain"]
                        )
                        print(
                            "live: native Codex read the selected original; "
                            "unselected file withheld; "
                            "message ID and attachment badges verified; checkout unchanged",
                            flush=True,
                        )
                    finally:
                        task = client.get(endpoint).json()
                        runtime = client.app.state.runtime
                        if task["status"] in ("running", "waiting"):
                            client.post(endpoint + "/interrupt", json={})
                        if task.get("thread_id") and runtime.rpc and runtime.rpc.connected:
                            client.portal.call(
                                runtime.rpc.call, "thread/archive", {"threadId": task["thread_id"]}
                            )
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
