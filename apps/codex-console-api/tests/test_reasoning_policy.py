import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from conftest import new_task, send_message

from codex_console.config import Settings
from codex_console.runtime import Runtime


def catalog_row(efforts, default="medium", model="model"):
    return {
        "model": model,
        "displayName": model,
        "isDefault": True,
        "defaultReasoningEffort": default,
        "supportedReasoningEfforts": [{"reasoningEffort": effort} for effort in efforts],
    }


def test_catalog_uses_configured_policy_not_native_order_or_blocked_names():
    settings = Settings.model_construct()
    rpc = SimpleNamespace(
        call=AsyncMock(
            return_value={
                "data": [
                    catalog_row(["ultra", "high", "future-effort", "xhigh", "max", "low"]),
                    catalog_row(["max", "future-effort"], model="no-allowed-efforts"),
                ],
                "nextCursor": None,
            }
        )
    )
    runtime = Runtime(settings, None)
    result = asyncio.run(runtime.models(rpc))
    assert len(result) == 1
    assert result[0]["efforts"] == ["low", "high", "xhigh"]
    assert result[0]["default_effort"] == "xhigh"

    settings.allowed_reasoning_efforts = ["low", "future-effort"]
    result = asyncio.run(runtime.models(rpc))
    assert result[0]["efforts"] == ["low", "future-effort"]
    assert result[0]["default_effort"] == "future-effort"


def configure_catalog(client, monkeypatch, *, default="medium", inherited=None):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    original = rpc.call

    async def call(method, params):
        result = await original(method, params)
        if method == "model/list":
            result["data"] = [
                catalog_row(
                    ["max", "low", "ultra", "medium", "future-effort", "high", "xhigh"],
                    default,
                    row["model"],
                )
                for row in result["data"]
            ]
        if method in ("thread/start", "thread/resume"):
            result["reasoningEffort"] = inherited
        return result

    monkeypatch.setattr(rpc, "call", call)
    return rpc


@pytest.mark.parametrize("effort", ["max", "ultra", "future-effort"])
def test_disallowed_advertised_efforts_are_hidden_and_never_submitted(client, monkeypatch, effort):
    rpc = configure_catalog(client, monkeypatch)
    response = client.get("/api/codex/models")
    assert response.status_code == 200
    assert response.json()[0]["efforts"] == ["low", "medium", "high", "xhigh"]
    task = new_task(client)
    result = client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"operation_id": str(uuid4()), "text": "Inspect", "effort": effort},
    )
    assert result.status_code == 422
    assert result.json()["code"] == "effort_unavailable"
    assert not any(method == "turn/start" for method, _ in rpc.calls)
    assert send_message(client, new_task(client)).status_code == 200


@pytest.mark.parametrize(
    "default,inherited,model,explicit,expected",
    [
        ("medium", None, None, None, "medium"),
        ("ultra", "max", None, None, "xhigh"),
        ("ultra", "high", None, None, "high"),
        ("future-effort", None, None, None, "xhigh"),
        ("medium", "high", "another-model", None, "medium"),
        ("medium", "high", None, "xhigh", "xhigh"),
    ],
)
def test_new_turn_resolves_only_allowed_defaults(
    client, monkeypatch, default, inherited, model, explicit, expected
):
    rpc = configure_catalog(client, monkeypatch, default=default, inherited=inherited)
    task = new_task(client)
    response = client.post(
        f"/api/tasks/{task['id']}/messages",
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect",
            "model": model,
            "effort": explicit,
        },
    )
    assert response.status_code == 200
    assert response.json()["effort"] == expected
    turn = next(params for method, params in rpc.calls if method == "turn/start")
    assert turn["effort"] == expected
    assert turn["collaborationMode"]["settings"]["reasoning_effort"] == expected
