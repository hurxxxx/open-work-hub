from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import os
import socket
from contextlib import asynccontextmanager
from functools import lru_cache
from threading import RLock
from typing import Annotated, Any

import httpx
from docker.errors import DockerException
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from open_work_hub_api.domains.hermes_terminal.broker_runtime import (
    BrokerRuntimeError,
    HermesTerminalBrokerRuntime,
)


async def _workspace_quota_watchdog() -> None:
    while True:
        try:
            await asyncio.to_thread(runtime().enforce_workspace_quotas)
        except Exception:
            # The watchdog is a safety loop. A transient Docker/API failure
            # must not permanently disable quota enforcement.
            pass
        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    watchdog = asyncio.create_task(_workspace_quota_watchdog())
    try:
        yield
    finally:
        watchdog.cancel()
        await asyncio.gather(watchdog, return_exceptions=True)


app = FastAPI(
    title="Open Work Hub Hermes Terminal Broker",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
_ATTACHMENT_GUARD = RLock()
_ATTACHED_SESSION_IDS: set[str] = set()


@app.exception_handler(DockerException)
async def docker_unavailable_handler(
    _request: Request,
    _error: DockerException,
) -> JSONResponse:
    return JSONResponse(
        {"detail": {"code": "hermes_terminal.docker_unavailable"}},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


class ResizeRequest(BaseModel):
    cols: int = Field(ge=20, le=500)
    rows: int = Field(ge=5, le=300)


class BrokerSessionCreateRequest(BaseModel):
    session_id: str
    profile_key: str
    mode: str
    cols: int = Field(ge=20, le=500)
    rows: int = Field(ge=5, le=300)
    mcp_url: str
    mcp_token: str
    research_sources: dict[str, bool]
    profile_archive_base64: str | None = None


class BrokerSessionResponse(BaseModel):
    session_id: str
    runtime_handle: str
    broker_instance_id: str
    status: str
    exit_code: int | None = None
    failure_code: str | None = None
    resource_namespace: str | None = None


class BrokerResourceReconcileRequest(BaseModel):
    known_session_ids: set[str] = Field(default_factory=set, max_length=5000)


class BrokerResourceReconcileResponse(BaseModel):
    removed_runners: int
    removed_workspaces: int
    removed_utilities: int


class BrokerFileEntry(BaseModel):
    relative_path: str
    name: str
    kind: str
    size_bytes: int | None = None
    modified_at: str | None = None


class BrokerFileListResponse(BaseModel):
    path: str
    items: list[BrokerFileEntry]


def normalize_relative_path(value: str | None, *, allow_root: bool = True) -> str:
    from pathlib import PurePosixPath

    raw = (value or "").replace("\\", "/").strip()
    if not raw or raw == ".":
        if allow_root:
            return ""
        raise ValueError("A file path is required.")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("The path must stay inside the session workspace.")
    normalized = path.as_posix()
    if len(normalized) > 1024:
        raise ValueError("The path is too long.")
    return normalized


def _broker_token() -> str:
    secret = os.environ.get("OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET", "").strip()
    if not secret:
        return ""
    return hmac.new(
        secret.encode(),
        b"open-work-hub-hermes-terminal-broker:v1",
        hashlib.sha256,
    ).hexdigest()


def require_broker_auth(authorization: str | None = Header(default=None)) -> None:
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    expected = _broker_token()
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@lru_cache(maxsize=1)
def runtime() -> HermesTerminalBrokerRuntime:
    return HermesTerminalBrokerRuntime()


def _runtime_error(error: BrokerRuntimeError) -> HTTPException:
    if error.code.endswith("not_found"):
        status_code = status.HTTP_404_NOT_FOUND
    elif error.code in {
        "hermes_terminal.session_active",
        "hermes_terminal.session_exists",
        "hermes_terminal.session_not_running",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif error.code.endswith("invalid") or error.code.endswith("too_large"):
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HTTPException(status_code=status_code, detail={"code": error.code})


class _DockerAttachment:
    def __init__(self, attached: Any) -> None:
        self._attached = attached
        raw_socket = getattr(attached, "_sock", attached)
        if not isinstance(raw_socket, socket.socket):
            try:
                attached.close()
            except Exception:
                pass
            raise BrokerRuntimeError("hermes_terminal.attach_failed")
        self._socket = raw_socket
        try:
            self._socket.setblocking(False)
        except OSError as exc:
            self.close()
            raise BrokerRuntimeError("hermes_terminal.attach_failed") from exc
        self._closed = False

    async def receive(self, max_bytes: int) -> bytes:
        return await asyncio.get_running_loop().sock_recv(self._socket, max_bytes)

    async def send(self, data: bytes) -> None:
        await asyncio.get_running_loop().sock_sendall(self._socket, data)

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        self._closed = True
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass
        if self._attached is not self._socket:
            try:
                self._attached.close()
            except Exception:
                pass


@app.get("/healthz")
async def healthz() -> Response:
    try:
        broker = await asyncio.to_thread(runtime)
        return JSONResponse(await asyncio.to_thread(broker.healthcheck))
    except BrokerRuntimeError as error:
        return JSONResponse(
            {"ready": False, "code": error.code},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@app.post(
    "/v1/sessions",
    response_model=BrokerSessionResponse,
    dependencies=[Depends(require_broker_auth)],
)
async def create_session(payload: BrokerSessionCreateRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            runtime().create_session,
            session_id=payload.session_id,
            profile_key=payload.profile_key,
            mode=payload.mode,
            cols=payload.cols,
            rows=payload.rows,
            mcp_url=payload.mcp_url,
            mcp_token=payload.mcp_token,
            research_sources=payload.research_sources,
            profile_archive_base64=payload.profile_archive_base64,
        )
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.get(
    "/v1/sessions/{session_id}",
    response_model=BrokerSessionResponse,
    dependencies=[Depends(require_broker_auth)],
)
async def get_session(session_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(runtime().session_status, session_id)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.post(
    "/v1/sessions/{session_id}/stop",
    response_model=BrokerSessionResponse,
    dependencies=[Depends(require_broker_auth)],
)
async def stop_session(session_id: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(runtime().stop_session, session_id)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.delete(
    "/v1/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_broker_auth)],
)
async def forget_session(session_id: str) -> Response:
    try:
        await asyncio.to_thread(runtime().forget_session, session_id)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/v1/resources",
    dependencies=[Depends(require_broker_auth)],
)
async def inventory_resources() -> dict[str, Any]:
    try:
        return await asyncio.to_thread(runtime().inventory)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.post(
    "/v1/resources/reconcile",
    response_model=BrokerResourceReconcileResponse,
    dependencies=[Depends(require_broker_auth)],
)
async def reconcile_resources(
    payload: BrokerResourceReconcileRequest,
) -> dict[str, int]:
    try:
        return await asyncio.to_thread(
            runtime().reconcile_resources,
            known_session_ids=payload.known_session_ids,
        )
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.post(
    "/v1/sessions/{session_id}/resize",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_broker_auth)],
)
async def resize_session(session_id: str, payload: ResizeRequest) -> Response:
    try:
        await asyncio.to_thread(
            runtime().resize_session,
            session_id,
            cols=payload.cols,
            rows=payload.rows,
        )
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/v1/sessions/{session_id}/files",
    response_model=BrokerFileListResponse,
    dependencies=[Depends(require_broker_auth)],
)
async def list_files(
    session_id: str,
    path: Annotated[str, Query(max_length=1024)] = "",
) -> dict[str, Any]:
    try:
        relative_path = normalize_relative_path(path)
        return await asyncio.to_thread(
            runtime().list_files,
            session_id,
            path=relative_path,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "hermes_terminal.path_invalid"},
        ) from error
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error


@app.get(
    "/v1/sessions/{session_id}/file",
    dependencies=[Depends(require_broker_auth)],
)
async def read_file(
    session_id: str,
    path: Annotated[str, Query(min_length=1, max_length=1024)],
) -> Response:
    try:
        relative_path = normalize_relative_path(path, allow_root=False)
        data = await asyncio.to_thread(runtime().read_file, session_id, path=relative_path)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "hermes_terminal.path_invalid"},
        ) from error
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error
    return Response(data, media_type="application/octet-stream")


@app.post(
    "/v1/sessions/{session_id}/profile/export",
    dependencies=[Depends(require_broker_auth)],
)
async def export_profile(session_id: str) -> Response:
    try:
        data = await asyncio.to_thread(runtime().export_profile, session_id)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error
    return Response(data, media_type="application/gzip")


@app.post(
    "/v1/sessions/{session_id}/workspace/export",
    dependencies=[Depends(require_broker_auth)],
)
async def export_workspace(session_id: str) -> Response:
    try:
        data = await asyncio.to_thread(runtime().export_workspace, session_id)
    except BrokerRuntimeError as error:
        raise _runtime_error(error) from error
    return Response(data, media_type="application/x-tar")


@app.api_route("/mcp/{session_id}", methods=["GET", "POST"])
async def relay_mcp(session_id: str, request: Request) -> Response:
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
    socket_path = os.environ.get(
        "OWH_HERMES_TERMINAL_MCP_SOCKET_PATH",
        "/run/open-work-hub/hermes-terminal-mcp.sock",
    ).strip()
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() in {"authorization", "accept", "content-type", "mcp-session-id"}
    }
    transport = httpx.AsyncHTTPTransport(uds=socket_path)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://open-work-hub"
        ) as client:
            upstream = await client.request(
                request.method,
                "/mcp",
                params={"session": session_id},
                headers=headers,
                content=body,
                timeout=360.0,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE) from exc
    response_headers = {
        name: value
        for name, value in upstream.headers.items()
        if name.lower() in {"content-type", "mcp-session-id"}
    }
    return Response(
        upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=None,
    )


@app.websocket("/v1/sessions/{session_id}/attach")
async def attach_session(websocket: WebSocket, session_id: str) -> None:
    authorization = websocket.headers.get("authorization")
    attachment: _DockerAttachment | None = None
    try:
        require_broker_auth(authorization)
        with _ATTACHMENT_GUARD:
            if session_id in _ATTACHED_SESSION_IDS:
                raise BrokerRuntimeError("hermes_terminal.session_already_attached")
            _ATTACHED_SESSION_IDS.add(session_id)
        attached, _container = await asyncio.to_thread(
            runtime().attach_socket,
            session_id,
        )
        attachment = _DockerAttachment(attached)
    except HTTPException:
        await websocket.close(code=4401)
        return
    except BrokerRuntimeError:
        with _ATTACHMENT_GUARD:
            _ATTACHED_SESSION_IDS.discard(session_id)
        await websocket.close(code=4409)
        return
    assert attachment is not None
    await websocket.accept()
    await websocket.send_json({"type": "ready", "active": True})

    async def send_output() -> None:
        empty_reads = 0
        while True:
            try:
                data = await attachment.receive(65536)
            except OSError:
                data = b""
            if data:
                empty_reads = 0
                await websocket.send_json(
                    {"type": "output", "data": base64.b64encode(data).decode("ascii")}
                )
                continue
            empty_reads += 1
            try:
                terminal_status = await asyncio.to_thread(
                    runtime().session_status,
                    session_id,
                )
            except BrokerRuntimeError as error:
                await websocket.send_json({"type": "error", "code": error.code})
                return
            if terminal_status.get("status") not in {"starting", "running"}:
                await websocket.send_json(
                    {
                        "type": "exit",
                        "status": terminal_status.get("status"),
                        "exit_code": terminal_status.get("exit_code"),
                        "failure_code": terminal_status.get("failure_code"),
                    }
                )
                return
            if empty_reads >= 20:
                await websocket.send_json({"type": "error", "code": "hermes_terminal.attach_eof"})
                return
            await asyncio.sleep(0.1)

    async def receive_input() -> None:
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > 100_000:
                await websocket.close(code=4400)
                return
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.close(code=4400)
                return
            if not isinstance(payload, dict):
                await websocket.close(code=4400)
                return
            message_type = payload.get("type")
            if message_type == "input":
                encoded = payload.get("data")
                if not isinstance(encoded, str) or len(encoded) > 90_000:
                    await websocket.close(code=4400)
                    return
                try:
                    data = base64.b64decode(encoded, validate=True)
                except binascii.Error:
                    await websocket.close(code=4400)
                    return
                if len(data) > 64 * 1024:
                    await websocket.close(code=4400)
                    return
                await attachment.send(data)
            elif message_type == "resize":
                cols = payload.get("cols")
                rows = payload.get("rows")
                if (
                    not isinstance(cols, int)
                    or not isinstance(rows, int)
                    or not 20 <= cols <= 500
                    or not 5 <= rows <= 300
                ):
                    await websocket.close(code=4400)
                    return
                await asyncio.to_thread(
                    runtime().resize_session,
                    session_id,
                    cols=cols,
                    rows=rows,
                )
            elif message_type == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await websocket.close(code=4400)
                return

    tasks = {
        asyncio.create_task(send_output()),
        asyncio.create_task(receive_input()),
    }
    try:
        done, _pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            if not task.cancelled():
                task.result()
    except (BrokerRuntimeError, OSError, RuntimeError, ValueError, WebSocketDisconnect):
        pass
    finally:
        for task in tasks:
            task.cancel()
        if attachment is not None:
            attachment.close()
        with _ATTACHMENT_GUARD:
            _ATTACHED_SESSION_IDS.discard(session_id)
        await asyncio.gather(*tasks, return_exceptions=True)
