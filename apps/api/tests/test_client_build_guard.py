import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from open_alm_api.client_build import ClientBuildGuardMiddleware


def test_websocket_build_guard_accepts_before_policy_close() -> None:
    downstream_called = False

    async def downstream(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        del scope, receive, send
        nonlocal downstream_called
        downstream_called = True

    middleware = ClientBuildGuardMiddleware(
        downstream,
        expected_build_id="build-current",
    )
    messages: list[dict[str, object]] = []

    async def receive() -> dict[str, str]:
        return {"type": "websocket.connect"}

    async def send(message) -> None:  # type: ignore[no-untyped-def]
        messages.append(message)

    asyncio.run(
        middleware(
            {
                "type": "websocket",
                "path": "/api/realtime",
                "query_string": b"__open_alm_build=build-old",
                "headers": [(b"host", b"app.test")],
            },
            receive,
            send,
        )
    )

    assert downstream_called is False
    assert messages == [
        {"type": "websocket.accept"},
        {
            "type": "websocket.close",
            "code": 4409,
            "reason": "CLIENT_BUILD_MISMATCH",
        },
    ]


def test_client_build_guard_short_circuits_stale_writes_before_handler() -> None:
    app = FastAPI()
    calls: list[dict[str, object]] = []

    @app.post("/api/write")
    async def write(payload: dict[str, object]) -> dict[str, bool]:
        calls.append(payload)
        return {"ok": True}

    app.add_middleware(
        ClientBuildGuardMiddleware,
        expected_build_id="build-current",
    )
    client = TestClient(app)

    stale_response = client.post(
        "/api/write",
        headers={
            "X-Open ALM-Web-Build": "build-old",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Dest": "empty",
        },
        json={"dangerous": True},
    )
    assert stale_response.status_code == 409
    assert calls == []

    current_response = client.post(
        "/api/write",
        headers={
            "X-Open ALM-Web-Build": "build-current",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Dest": "empty",
        },
        json={"dangerous": False},
    )
    assert current_response.status_code == 200
    assert calls == [{"dangerous": False}]
