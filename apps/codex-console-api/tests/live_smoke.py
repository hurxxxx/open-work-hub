"""Opt-in subscription smoke using only a disposable repository and database.

Run directly; never part of pytest/CI or an automatic model upgrade.
"""

import json
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

PLAN = (
    "Inspect this tiny Python project and create a concrete implementation and validation plan "
    "for adding clamp(value, "
    "lower, upper) to calculator.py. Accept int/float, return the nearest bound when "
    "outside the range, preserve an in-range value, and raise ValueError when lower > "
    "upper. Add unittest coverage for below, within, above and invalid bounds. Preserve "
    "add(). No external dependencies. All decisions are specified; no questions are "
    "necessary. Do not implement yet."
)


def main():
    url = make_url(os.environ["OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN"])
    name = "console_test_live_" + uuid4().hex
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
            password = str(uuid4()) + str(uuid4())
            with factory.begin() as db:
                db.add(Owner(password_hash=password_hash(password)))
            engine.dispose()
            with tempfile.TemporaryDirectory(prefix="codex-console-live-") as directory:
                root = Path(directory) / "dev"
                root.mkdir()
                for args in (
                    ("init", "-b", "dev"),
                    ("config", "user.name", "Console Smoke"),
                    ("config", "user.email", "console@test.invalid"),
                ):
                    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
                (root / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
                (root / ".gitignore").write_text("__pycache__/\n")
                subprocess.run(["git", "-C", str(root), "add", "."], check=True)
                subprocess.run(
                    ["git", "-C", str(root), "commit", "-m", "fixture"],
                    check=True,
                    capture_output=True,
                )
                settings = Settings(
                    database_url=target,
                    origin="http://localhost",
                    workspace=root,
                    web_dist=root / "absent",
                    _env_file=None,
                )
                with TestClient(create_app(settings), base_url="http://localhost") as client:
                    client.headers["origin"] = settings.origin
                    assert (
                        client.post("/api/session", json={"password": password}).status_code == 200
                    )
                    client.headers["x-csrf-token"] = client.cookies[CSRF_COOKIE]
                    account = client.get("/api/codex/account").json()
                    assert account.get("auth_type") == "chatgpt", account.get("error_code")
                    print("live: ChatGPT subscription authenticated", flush=True)
                    task = client.post(
                        "/api/tasks", json={"title": "Temporary subscription smoke"}
                    ).json()
                    task_id = task["id"]

                    def request(path, body):
                        response = client.post(f"/api/tasks/{task_id}/{path}", json=body)
                        if response.status_code != 200:
                            raise RuntimeError(response.json().get("code", "request_failed"))
                        return response.json()

                    def finish():
                        deadline = time.monotonic() + 300
                        while time.monotonic() < deadline:
                            state = client.get(f"/api/tasks/{task_id}").json()
                            if state["requests"]:
                                raise RuntimeError("Live smoke requires an interactive response")
                            if state["status"] not in ("starting", "running", "waiting"):
                                if state["status"] != "idle":
                                    raise RuntimeError(state["error_code"] or state["status"])
                                return state
                            time.sleep(1)
                        raise RuntimeError("Live smoke timed out")

                    try:
                        request(
                            "messages",
                            {
                                "operation_id": str(uuid4()),
                                "stage": "plan",
                                "text": PLAN,
                            },
                        )
                        task = finish()
                        revision = next(
                            r for r in reversed(task["revisions"]) if r["kind"] == "plan"
                        )
                        assert not subprocess.check_output(
                            ["git", "-C", str(root), "status", "--porcelain"]
                        )
                        print("live: plan complete; checkout unchanged", flush=True)
                        request(
                            "implement",
                            {"operation_id": str(uuid4()), "revision_id": revision["id"]},
                        )
                        task = finish()
                        checks = subprocess.run(
                            [
                                "python3",
                                "-c",
                                (
                                    "import unittest; s=unittest.defaultTestLoader.discover('.'); "
                                    "assert s.countTestCases()>=4; "
                                    "r=unittest.TextTestRunner().run(s); "
                                    "raise SystemExit(not r.wasSuccessful())"
                                ),
                            ],
                            cwd=root,
                            capture_output=True,
                            timeout=30,
                        )
                        assert checks.returncode == 0, "Generated behavior checks did not pass"
                        changes = client.get(f"/api/tasks/{task_id}/changes").json()
                        assert changes and task["stage"] == "review"
                        print(
                            json.dumps(
                                {
                                    "live": "implementation verified",
                                    "changed_files": len(changes),
                                    "minimum_tests_passed": 4,
                                }
                            ),
                            flush=True,
                        )
                    finally:
                        current = client.get(f"/api/tasks/{task_id}").json()
                        runtime = client.app.state.runtime
                        if current.get("turn_id") and current["status"] in ("running", "waiting"):
                            client.post(f"/api/tasks/{task_id}/interrupt", json={})
                        if current.get("thread_id") and runtime.rpc and runtime.rpc.connected:
                            client.portal.call(
                                runtime.rpc.call,
                                "thread/archive",
                                {"threadId": current["thread_id"]},
                            )
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
