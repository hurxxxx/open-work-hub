import json
import os
import subprocess
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import make_url

from codex_console.app import create_app
from codex_console.auth import CSRF_COOKIE, password_hash
from codex_console.cli import migrate
from codex_console.config import Settings
from codex_console.models import Owner, database
from codex_console.rpc import CONTRACT, METHOD_SCHEMAS

PASSWORD = "console-tests-only-password"


class FakeRPC:
    def __init__(self, binary, cwd, on_message, on_disconnect):
        self.cwd = str(cwd)
        self.generation = str(uuid4())
        self.connected = False
        self.calls = []
        self.responses = []
        self.threads = {}
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        self.auth_type = "chatgpt"
        self.fail_turn = False
        self.policies = {}
        self.config_model = None
        self.config_effort = None

    async def start(self):
        self.connected = True

    async def close(self):
        self.connected = False

    async def call(self, method, params):
        from jsonschema import Draft7Validator

        from codex_console.errors import ConsoleError

        if method in METHOD_SCHEMAS:
            Draft7Validator(CONTRACT["schemas"][METHOD_SCHEMAS[method]]).validate(params)
        self.calls.append((method, params))
        if method == "account/read":
            return {"account": {"type": self.auth_type, "planType": "test"}}
        if method == "account/rateLimits/read":
            return {"rateLimits": {"primary": {"usedPercent": 10}}}
        if method == "model/list":
            return {
                "data": [
                    {
                        "model": name,
                        "displayName": name,
                        "isDefault": i == 0,
                        "defaultReasoningEffort": "medium",
                        "supportedReasoningEfforts": [
                            {"reasoningEffort": effort} for effort in ("low", "medium", "high")
                        ],
                    }
                    for i, name in enumerate(("account-default", "another-model"))
                ],
                "nextCursor": None,
            }
        if method == "config/read":
            return {
                "config": {
                    "model": self.config_model,
                    "model_reasoning_effort": self.config_effort,
                    "model_provider": None,
                    "mcp_servers": {"example": {}},
                }
            }
        if method in ("thread/start", "thread/resume"):
            thread_id = params.get("threadId") or str(uuid4())
            self.threads.setdefault(
                thread_id,
                {
                    "id": thread_id,
                    "cwd": params["cwd"],
                    "status": {"type": "idle"},
                    "turns": [],
                    "model": self.config_model or "account-default",
                    "reasoningEffort": self.config_effort or "medium",
                },
            )
            return {
                "thread": self.threads[thread_id],
                "model": self.threads[thread_id]["model"],
                "reasoningEffort": self.threads[thread_id]["reasoningEffort"],
                "modelProvider": "openai",
                "cwd": self.threads[thread_id]["cwd"],
                "sandbox": self.policies.get(thread_id, {"type": "readOnly"}),
            }
        if method == "turn/start":
            if self.fail_turn:
                raise ConsoleError("codex_request_uncertain", 503)
            self.threads[params["threadId"]]["model"] = params["model"]
            self.threads[params["threadId"]]["reasoningEffort"] = params["effort"]
            self.policies[params["threadId"]] = {
                **params["sandboxPolicy"],
                **(
                    {"writableRoots": []}
                    if params["sandboxPolicy"].get("writableRoots") == [params["cwd"]]
                    else {}
                ),
            }
            self.threads[params["threadId"]]["cwd"] = params["cwd"]
            return {"turn": {"id": str(uuid4()), "status": "inProgress", "items": []}}
        if method == "thread/read":
            return {"thread": self.threads[params["threadId"]]}
        if method == "thread/list":
            return {"data": [], "nextCursor": None}
        return {}

    async def respond(self, request_id, result):
        self.responses.append((request_id, result))

    async def send(self, message):
        self.responses.append(message)


@pytest.fixture(scope="session")
def database_url():
    template = os.environ.get("OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN")
    if not template:
        pytest.skip(
            "Set OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN to a non-production PostgreSQL 18 DB"
        )
    url = make_url(template)
    name = "console_test_" + uuid4().hex
    connection = psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    )
    connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    target = url.set(drivername="postgresql+psycopg", database=name).render_as_string(
        hide_password=False
    )
    migrate(target)
    yield target
    connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
    connection.close()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "dev"
    root.mkdir()
    for args in (
        ("init", "-b", "dev"),
        ("config", "user.email", "console@test.invalid"),
        ("config", "user.name", "Console Test"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (root / "hello.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(root), "add", "hello.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-m", "fixture"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(root), "update-ref", "refs/remotes/origin/dev", "HEAD"], check=True
    )
    return root


@pytest.fixture
def settings(database_url, repository):
    return Settings(
        database_url=database_url,
        origin="http://localhost",
        workspace=repository,
        worktree_root=repository.parent / "worktrees",
        web_dist=repository / "absent",
        attachment_cache=repository.parent / "attachments",
        _env_file=None,
    )


@pytest.fixture
def client(settings):
    engine, factory = database(settings.database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE console_owner, console_sessions, console_tasks, "
                "console_workspace_lease RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(text("INSERT INTO console_workspace_lease (id) VALUES (1)"))
    with factory.begin() as db:
        db.add(Owner(password_hash=password_hash(PASSWORD)))
    app = create_app(settings, rpc_factory=FakeRPC)
    with TestClient(app, base_url="http://localhost") as browser:
        browser.headers["origin"] = settings.origin
        result = browser.post("/api/session", json={"password": PASSWORD})
        assert result.status_code == 200
        browser.headers["x-csrf-token"] = browser.cookies[CSRF_COOKIE]
        yield browser
    engine.dispose()


def new_task(client, title="A useful change"):
    result = client.post("/api/tasks", json={"title": title})
    assert result.status_code == 200
    return result.json()


def send_message(client, task, stage="plan", text="Inspect the repository", operation_id=None):
    return client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"text": text, "stage": stage, "operation_id": operation_id or str(uuid4())},
    )


def notify(client, task, method, extra):
    client.portal.call(
        client.app.state.runtime.on_message,
        {
            "method": method,
            "params": {"threadId": task["thread_id"], "turnId": task["turn_id"], **extra},
        },
    )


def planning_text(answer, documents=()):
    return json.dumps({"answer": answer, "documents": list(documents)})


def complete(client, task, body="An actionable plan", status="completed", *, documents=None):
    if task["stage"] == "plan":
        item = (
            {"id": str(uuid4()), "type": "plan", "text": body}
            if documents is None
            else {
                "id": str(uuid4()),
                "type": "agentMessage",
                "phase": "final_answer",
                "text": planning_text(body, documents),
            }
        )
    else:
        item = {
            "id": str(uuid4()),
            "type": "agentMessage",
            "phase": "final_answer",
            "text": body,
        }
    notify(client, task, "item/completed", {"item": item})
    notify(client, task, "turn/completed", {"turn": {"id": task["turn_id"], "status": status}})
    return client.get(f"/api/tasks/{task['id']}").json()


def plan(client):
    task = new_task(client)
    task = send_message(client, task, "plan").json()
    return complete(client, task)
