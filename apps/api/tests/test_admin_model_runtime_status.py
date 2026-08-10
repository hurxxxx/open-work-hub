from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.admin import model_runtime_status_router
from open_work_hub_api.domains.admin import model_runtime_status_service
from open_work_hub_api.domains.admin.model_runtime_status_schemas import (
    AdminModelRuntimeStatusResponse,
    ModelRuntimeModelResponse,
    ModelRuntimeTargetResponse,
)
from open_work_hub_api.domains.admin.model_runtime_status_service import (
    collect_model_runtime_status,
)
from tests.dev_accounts import auth_headers, dev_login


def _settings(**overrides: object) -> Settings:
    values = {
        "postgres_dsn": ("postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test"),
        "inference_gateway_base_url": "http://current-server:18080",
        "inference_gateway_api_key": "gateway-secret",
        "llm_local_base_url": "http://local-llm:8000/v1",
        "llm_local_api_key": "llm-secret",
        "model_status_diagnostic_targets_json": json.dumps(
            [
                {
                    "id": "local-model-a",
                    "display_name": "Local Model A",
                    "endpoint_url": "http://local-model-a:8000/v1",
                    "provider_id": "local",
                    "role": "redundancy",
                },
                {
                    "id": "local-model-b",
                    "display_name": "Local Model B",
                    "endpoint_url": "http://local-model-b:8001/v1",
                    "provider_id": "local",
                    "role": "redundancy",
                },
            ]
        ),
    }
    values.update(overrides)
    return Settings(**values)


def _gateway_health() -> dict[str, object]:
    return {
        "ready": True,
        "models": {
            "embedding": {
                "task": "embedding",
                "model": "dragonkue/snowflake-arctic-embed-l-v2.0-ko",
                "loaded": True,
            },
            "asr": {
                "task": "asr",
                "model": "CohereLabs/cohere-transcribe-03-2026",
                "loaded": True,
            },
        },
    }


def _llm_models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [{"id": "legacy-env-model", "object": "model"}],
    }


@pytest.mark.anyio
async def test_model_runtime_status_collects_current_server_and_local_targets() -> None:
    seen_authorization: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(request.headers.get("authorization", ""))
        if request.url.host == "current-server":
            return httpx.Response(200, json=_gateway_health())
        return httpx.Response(200, json=_llm_models())

    snapshot = await collect_model_runtime_status(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    assert snapshot.status == "online"
    assert [target.id for target in snapshot.targets] == [
        "inference-gateway",
        "local-llm",
        "local-model-a",
        "local-model-b",
    ]
    assert snapshot.targets[0].models == [
        ModelRuntimeModelResponse(
            name="dragonkue/snowflake-arctic-embed-l-v2.0-ko",
            task="embedding",
            loaded=True,
        ),
        ModelRuntimeModelResponse(
            name="CohereLabs/cohere-transcribe-03-2026",
            task="asr",
            loaded=True,
        ),
    ]
    assert seen_authorization == [
        "Bearer gateway-secret",
        "Bearer llm-secret",
        "Bearer llm-secret",
        "Bearer llm-secret",
    ]


@pytest.mark.anyio
async def test_model_runtime_status_prefers_admin_provider_default(
    monkeypatch,
) -> None:
    selected_model = "unsloth/Qwen3.6-35B-A3B-NVFP4-Fast"

    class FakeDb:
        def get(self, *_args):
            return None

    db = FakeDb()

    monkeypatch.setattr(
        model_runtime_status_service,
        "get_ai_model_provider_default_model_key",
        lambda received_db, *, provider_id: (
            selected_model
            if received_db is db and provider_id == "local"
            else None
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "current-server":
            return httpx.Response(200, json=_gateway_health())
        return httpx.Response(
            200,
            json={"data": [{"id": selected_model, "object": "model"}]},
        )

    snapshot = await collect_model_runtime_status(
        _settings(),
        db=db,  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),
    )

    assert snapshot.status == "online"
    assert all(target.status == "online" for target in snapshot.targets)


@pytest.mark.anyio
async def test_model_runtime_status_preserves_partial_results_without_leaking_errors(
    monkeypatch,
) -> None:
    selected_model = "admin-selected-model"

    class FakeDb:
        def get(self, *_args):
            return None

    db = FakeDb()
    monkeypatch.setattr(
        model_runtime_status_service,
        "get_ai_model_provider_default_model_key",
        lambda received_db, *, provider_id: (
            selected_model
            if received_db is db and provider_id == "local"
            else None
        ),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "current-server":
            return httpx.Response(200, json=_gateway_health())
        if request.url.host == "dgx-102":
            raise httpx.ConnectError("secret internal network detail", request=request)
        if request.url.host == "dgx-103":
            return httpx.Response(200, json={"unexpected": "payload"})
        return httpx.Response(200, json={"data": [{"id": "different-model"}]})

    snapshot = await collect_model_runtime_status(
        _settings(),
        db=db,  # type: ignore[arg-type]
        transport=httpx.MockTransport(handler),
    )
    payload = snapshot.model_dump_json()

    assert snapshot.status == "degraded"
    assert snapshot.targets[0].status == "online"
    assert snapshot.targets[1].status == "degraded"
    assert snapshot.targets[1].error_code == "model_missing"
    assert snapshot.targets[2].status == "offline"
    assert snapshot.targets[2].error_code == "connection_failed"
    assert snapshot.targets[3].status == "offline"
    assert snapshot.targets[3].error_code == "invalid_response"
    assert "secret internal network detail" not in payload
    assert "gateway-secret" not in payload
    assert "llm-secret" not in payload


@pytest.mark.anyio
async def test_model_runtime_status_surfaces_invalid_dynamic_inventory() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "current-server":
            return httpx.Response(200, json=_gateway_health())
        return httpx.Response(200, json=_llm_models())

    snapshot = await collect_model_runtime_status(
        _settings(model_status_diagnostic_targets_json='{"not":"a-list"}'),
        transport=httpx.MockTransport(handler),
    )

    assert snapshot.status == "degraded"
    assert snapshot.targets[-1].error_code == "configuration_invalid"


def test_admin_model_runtime_status_requires_platform_admin(client: TestClient) -> None:
    headers = auth_headers(dev_login(client, "delivery-hub-member")["token"])

    response = client.get("/api/v1/admin/model-runtime-status", headers=headers)

    assert response.status_code == 403


def test_admin_model_runtime_status_returns_snapshot(
    client: TestClient,
    monkeypatch,
) -> None:
    received_db = None

    async def fake_collect(*, db) -> AdminModelRuntimeStatusResponse:
        nonlocal received_db
        received_db = db
        return AdminModelRuntimeStatusResponse(
            checked_at=datetime(2026, 7, 13, 2, 0, tzinfo=timezone.utc),
            status="online",
            targets=[
                ModelRuntimeTargetResponse(
                    id="inference-gateway",
                    display_name="Inference gateway",
                    kind="inference_gateway",
                    role="diagnostic",
                    status="online",
                    models=[ModelRuntimeModelResponse(name="embedding", loaded=True)],
                )
            ],
        )

    monkeypatch.setattr(
        model_runtime_status_router,
        "collect_model_runtime_status",
        fake_collect,
    )
    headers = auth_headers(dev_login(client)["token"])

    response = client.get("/api/v1/admin/model-runtime-status", headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["targets"][0]["models"][0]["name"] == "embedding"
    assert received_db is not None
