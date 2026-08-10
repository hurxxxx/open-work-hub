from __future__ import annotations

import asyncio
from types import SimpleNamespace

from starlette.websockets import WebSocketState

from open_work_hub_api.domains.collaboration import FastAPIYjsWebsocket


class _ConcurrentSendProbeWebSocket:
    client_state = WebSocketState.CONNECTED
    application_state = WebSocketState.CONNECTED

    def __init__(self) -> None:
        self.active_sends = 0
        self.max_active_sends = 0
        self.sent_messages: list[bytes] = []

    async def send_bytes(self, message: bytes) -> None:
        self.active_sends += 1
        self.max_active_sends = max(self.max_active_sends, self.active_sends)
        await asyncio.sleep(0)
        self.sent_messages.append(message)
        await asyncio.sleep(0)
        self.active_sends -= 1


class _FailingSendWebSocket:
    client_state = WebSocketState.CONNECTED
    application_state = WebSocketState.CONNECTED

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.send_attempts = 0

    async def send_bytes(self, _message: bytes) -> None:
        self.send_attempts += 1
        raise self.exc


def _runtime_stub() -> SimpleNamespace:
    return SimpleNamespace(
        room=SimpleNamespace(clients=[]),
        last_editor_user_id=None,
    )


def test_fastapi_yjs_websocket_serializes_concurrent_sends() -> None:
    async def exercise() -> None:
        probe = _ConcurrentSendProbeWebSocket()
        runtime = _runtime_stub()
        websocket = FastAPIYjsWebsocket(
            probe,  # type: ignore[arg-type]
            "whiteboard:board-1",
            runtime,  # type: ignore[arg-type]
            "user-1",
        )

        await asyncio.gather(
            websocket.send(b"first"),
            websocket.send(b"second"),
            websocket.send(b"third"),
        )

        assert probe.sent_messages == [b"first", b"second", b"third"]
        assert probe.max_active_sends == 1

    asyncio.run(exercise())


def test_fastapi_yjs_websocket_treats_websockets_assertion_as_closed_send() -> None:
    async def exercise() -> None:
        probe = _FailingSendWebSocket(AssertionError())
        runtime = _runtime_stub()
        websocket = FastAPIYjsWebsocket(
            probe,  # type: ignore[arg-type]
            "whiteboard:board-1",
            runtime,  # type: ignore[arg-type]
            "user-1",
        )
        runtime.room.clients.append(websocket)

        await websocket.send(b"message")
        await websocket.send(b"ignored-after-terminal-error")

        assert probe.send_attempts == 1
        assert runtime.room.clients == []

    asyncio.run(exercise())
