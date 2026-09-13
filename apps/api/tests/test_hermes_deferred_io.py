from __future__ import annotations

import asyncio
import base64
from datetime import timedelta
from io import BytesIO
import threading
from types import SimpleNamespace
from uuid import uuid4

from anyio import CapacityLimiter
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import CompanyAppControl, User
from open_work_hub_api.domains.hermes import file_router, files, mcp_router
from open_work_hub_api.domains.hermes.models import (
    HermesFileObject,
    HermesProfileBinding,
    HermesRunProjection,
    HermesSessionBinding,
    HermesSessionFile,
)
from open_work_hub_api.domains.hermes.repository import HermesRunRepository, utcnow_naive
from open_work_hub_api.domains.hermes.service import mcp_profile_bearer_secret


@pytest.fixture
def deferred_io(application_postgres_dsn, monkeypatch):
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(engine)
    state = SimpleNamespace(objects={}, calls=[], on_io=None, factory=factory)

    class Body(BytesIO):
        def release_conn(self):
            pass

    class Store:
        def put_object(self, _bucket, key, data, length, **kwargs):
            state.calls.append("write")
            state.objects[key] = data.read(length)
            if state.on_io:
                state.on_io()

        def get_object(self, _bucket, key):
            state.calls.append("read")
            if state.on_io:
                state.on_io()
            return Body(state.objects[key])

        def remove_object(self, _bucket, key):
            state.objects.pop(key, None)

    class ToolClient:
        def list_tools(self, *args, **kwargs):
            return [
                SimpleNamespace(
                    descriptor=SimpleNamespace(name="fixture.read", approval_policy="none"),
                    mcp_tool={"name": "fixture.read"},
                )
            ]

        def call_tool(self, *args, **kwargs):
            state.calls.append("tool")
            return {"ok": True}

    monkeypatch.setattr(files, "get_minio_client", lambda: Store())
    monkeypatch.setattr(files, "ensure_bucket", lambda: None)
    monkeypatch.setattr(mcp_router, "AiMcpClient", ToolClient)
    monkeypatch.setattr(mcp_router, "get_session_factory", lambda: factory)
    settings = get_settings().model_copy(
        update={"hermes_mcp_shared_secret": SecretStr("synthetic-deferred-io-secret")}
    )
    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    with factory() as db:
        user = User(
            id=str(uuid4()),
            login_id=uuid4().hex,
            email="deferred@example.test",
            full_name="Deferred I/O test",
            password_hash="unused",
        )
        db.add(user)
        db.flush()
        profile = HermesProfileBinding(
            id=str(uuid4()),
            user_id=user.id,
            profile_name=f"owh-{uuid4().hex}",
            status="active",
            provider="openai",
            model="test",
        )
        db.add(profile)
        db.flush()
        session = HermesSessionBinding(
            id=str(uuid4()),
            user_id=user.id,
            profile_binding_id=profile.id,
            hermes_session_id=f"session-{uuid4().hex}",
        )
        db.add(session)
        db.merge(CompanyAppControl(app_id="chatbot", enabled=True))
        db.flush()
        db.merge(AppAccessPolicy(app_id="chatbot", audience="all"))
        run = HermesRunRepository(db).stage(
            binding=profile,
            session=session,
            input_text="test",
            instructions=None,
            conversation_history=[],
        )
        run.status, run.hermes_run_id = "running", "run_deferred_file"
        db.commit()
        row = files.save_file(db, session=session, path="saved.txt", data=b"original private bytes")
        state.run_id, state.user_id = run.id, user.id
        state.profile_id, state.session_id = profile.id, session.id
        state.file_id, state.old_key = row.id, row.object_key
        state.url = f"/internal/hermes/mcp?profile={profile.profile_name}"
        state.headers = {
            "Authorization": f"Bearer {mcp_profile_bearer_secret(settings, profile.profile_name)}",
            "X-Hermes-Run-Id": run.hermes_run_id,
        }
    state.calls.clear()

    def revoke(kind):
        with factory() as db:
            if kind == "stop":
                db.get(HermesRunProjection, state.run_id).status = "stopping"
            elif kind == "app":
                db.get(CompanyAppControl, "chatbot").enabled = False
            elif kind == "session":
                db.get(HermesSessionBinding, state.session_id).status = "deleted"
            elif kind == "profile":
                db.get(HermesProfileBinding, state.profile_id).status = "disabled"
            elif kind == "user":
                db.get(User, state.user_id).login_blocked = True
            db.commit()

    state.revoke = revoke
    app = FastAPI()
    app.include_router(mcp_router.router)
    app.include_router(file_router.router)

    def get_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db_session] = get_db
    app.dependency_overrides[require_current_user] = lambda: SimpleNamespace(id=state.user_id)
    state.app = app
    try:
        yield state
    finally:
        engine.dispose()


@pytest.mark.anyio
async def test_context_does_not_infer_physical_resources_from_database_namespace(
    deferred_io, monkeypatch
):
    state = deferred_io
    settings = mcp_router.get_settings().model_copy(
        update={"hermes_terminal_resource_namespace": "database-cutover-20260913"}
    )
    monkeypatch.setattr(mcp_router, "get_settings", lambda: settings)
    async with AsyncClient(
        transport=ASGITransport(app=state.app), base_url="http://test"
    ) as client:
        response = await client.post(
            state.url,
            headers=state.headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "owh/context", "params": {}},
        )
    assert response.status_code == 200
    context = response.json()["result"]
    assert context["allow_native_tools"] is True
    assert set(context["sandbox"]) == {"image", "no_proxy"}
    assert context["sandbox"]["image"] == mcp_router.HERMES_IMAGE
    assert "localhost" in context["sandbox"]["no_proxy"].split(",")


def payload(state, operation):
    params = (
        {"id": state.file_id}
        if operation == "read"
        else {"path": "saved.txt", "data": base64.b64encode(b"replacement").decode()}
        if operation == "write"
        else {"name": "fixture.read", "arguments": {}}
        if operation == "tool"
        else {}
    )
    return {
        "id": 1,
        "method": "tools/call" if operation == "tool" else f"owh/files/{operation}",
        "params": params,
    }


def assert_denied(response):
    assert response.status_code in (200, 403, 404, 409)
    body = response.json()
    assert response.status_code != 200 or "error" in body or body.get("result", {}).get("isError")
    assert "data" not in body.get("result", {})
    assert "original private bytes" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["list", "read", "write", "tool"])
@pytest.mark.parametrize("revocation", ["stop", "app", "session", "profile", "user", "unchanged"])
async def test_deferred_operations_recheck_current_authority(deferred_io, operation, revocation):
    state = deferred_io
    limiter = CapacityLimiter(1)
    token = mcp_router._OPERATION_THREADS.set(limiter)
    entered, release = threading.Event(), threading.Event()

    def hold():
        entered.set()
        assert release.wait(5)

    blocker = asyncio.create_task(mcp_router._run_callback(hold, operation=True))
    pending = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        async with AsyncClient(
            transport=ASGITransport(app=state.app), base_url="http://test"
        ) as client:
            pending = asyncio.create_task(
                client.post(state.url, headers=state.headers, json=payload(state, operation))
            )
            async with asyncio.timeout(2):
                while limiter.statistics().tasks_waiting != 1:
                    await asyncio.sleep(0.01)
            state.revoke(revocation)
            release.set()
            response = await asyncio.wait_for(pending, 2)
        if revocation == "unchanged":
            assert response.status_code == 200 and "error" not in response.json()
        else:
            assert_denied(response)
            assert state.calls == []
            with state.factory() as db:
                assert db.get(HermesSessionFile, state.file_id).object_key == state.old_key
    finally:
        release.set()
        await blocker
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        mcp_router._OPERATION_THREADS.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("revocation", ["stop", "app"])
async def test_revocation_during_storage_io_rejects_late_results(
    deferred_io, operation, revocation
):
    state = deferred_io
    state.on_io = lambda: state.revoke(revocation)
    async with AsyncClient(
        transport=ASGITransport(app=state.app), base_url="http://test"
    ) as client:
        response = await client.post(
            state.url, headers=state.headers, json=payload(state, operation)
        )
    assert_denied(response)
    with state.factory() as db:
        assert db.get(HermesSessionFile, state.file_id).object_key == state.old_key
        assert list(db.scalars(select(HermesSessionFile.id))) == [state.file_id]
        if operation == "write":
            orphan = db.scalar(
                select(HermesFileObject).where(HermesFileObject.object_key != state.old_key)
            )
            assert orphan is not None and orphan.object_key in state.objects
            assert orphan.expires_at < utcnow_naive() + timedelta(hours=2)
            orphan.expires_at = utcnow_naive() - timedelta(seconds=1)
            db.commit()
            assert files.cleanup_files(db) == 1
            assert list(state.objects) == [state.old_key]


@pytest.mark.anyio
async def test_public_upload_revoked_during_storage_preserves_saved_content(deferred_io):
    state = deferred_io
    with state.factory() as db:
        db.get(HermesRunProjection, state.run_id).status = "completed"
        db.commit()
    state.on_io = lambda: state.revoke("app")
    async with AsyncClient(
        transport=ASGITransport(app=state.app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/sessions/{state.session_id}/files",
            headers={"Content-Type": "application/octet-stream", "X-File-Name": "saved.txt"},
            content=b"replacement",
        )
    assert response.status_code == 422
    with state.factory() as db:
        assert db.get(HermesSessionFile, state.file_id).object_key == state.old_key
