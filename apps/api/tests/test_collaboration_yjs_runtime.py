from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from starlette.websockets import WebSocketDisconnect, WebSocketState

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


async def _allow_frame() -> None:
    return None


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
            authorize=_allow_frame,
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
            authorize=_allow_frame,
        )
        runtime.room.clients.append(websocket)

        await websocket.send(b"message")
        await websocket.send(b"ignored-after-terminal-error")

        assert probe.send_attempts == 1
        assert runtime.room.clients == []

    asyncio.run(exercise())


class _RevocationProbeWebSocket(_ConcurrentSendProbeWebSocket):
    def __init__(self):
        super().__init__()
        self.incoming = asyncio.Queue()
        self.close_codes = []

    async def receive(self):
        return await self.incoming.get()

    async def close(self, code, reason=None):
        self.close_codes.append(code)
        self.application_state = WebSocketState.DISCONNECTED


@pytest.mark.parametrize("direction", ["receive", "send"])
@pytest.mark.parametrize("denial", [False, 403])
def test_yjs_revocation_blocks_each_frame_before_disclosure_or_room_mutation(direction, denial):
    async def exercise():
        probe = _RevocationProbeWebSocket()
        runtime = _runtime_stub()
        allowed = True

        async def authorize():
            if not allowed:
                if denial == 403:
                    raise HTTPException(status_code=403)
                return False
            return True

        transport = FastAPIYjsWebsocket(probe, "docs:doc-1", runtime, "editor", authorize=authorize)
        runtime.room.clients.append(transport)
        await transport.send(b"authorized")
        allowed = False
        if direction == "send":
            await asyncio.wait_for(transport.send(b"private-after-revocation"), timeout=1)
        else:
            probe.incoming.put_nowait({"type": "websocket.receive", "bytes": b"\x00update"})
            with pytest.raises(WebSocketDisconnect):
                await asyncio.wait_for(transport.recv(), timeout=1)
        assert probe.sent_messages == [b"authorized"]
        assert runtime.last_editor_user_id is None
        assert runtime.room.clients == []
        assert probe.close_codes == [1008]

    asyncio.run(exercise())


def test_yjs_queued_send_rechecks_after_waiting_for_send_lock():
    async def exercise():
        probe = _RevocationProbeWebSocket()
        allowed = True

        async def authorize():
            return allowed

        transport = FastAPIYjsWebsocket(
            probe, "whiteboard:board-1", _runtime_stub(), "editor", authorize=authorize
        )
        async with transport._send_lock:
            pending = asyncio.create_task(transport.send(b"queued-private-content"))
            await asyncio.sleep(0)
            allowed = False
        await asyncio.wait_for(pending, timeout=1)
        assert not probe.sent_messages
        assert probe.close_codes == [1008]

    asyncio.run(exercise())
