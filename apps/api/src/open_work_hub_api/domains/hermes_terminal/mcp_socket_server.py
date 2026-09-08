from __future__ import annotations

import asyncio
import fcntl
import os
import stat
from pathlib import Path
from typing import TextIO

import httpx
import uvicorn
from fastapi import FastAPI

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.hermes_terminal.mcp_router import router


def create_mcp_socket_app() -> FastAPI:
    socket_app = FastAPI(
        title="Open Work Hub Hermes Terminal MCP",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    socket_app.include_router(router)

    @socket_app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ready": True}

    return socket_app


class HermesTerminalMcpSocketServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(settings.hermes_terminal_mcp_socket_path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")
        self.server: uvicorn.Server | None = None
        self.task: asyncio.Task[None] | None = None
        self._lock_file: TextIO | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._shared_socket = False

    async def startup(self) -> None:
        if not self.settings.hermes_enabled:
            return
        if self.task is not None or self._shared_socket:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._try_acquire_lock():
            await self._wait_for_shared_socket_or_lock()
            if self._shared_socket:
                return

        if await self._socket_is_healthy():
            self._release_lock()
            self._shared_socket = True
            return

        try:
            mode = self.path.lstat().st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISSOCK(mode):
                self._release_lock()
                raise RuntimeError(
                    f"Hermes terminal MCP socket path exists and is not a Unix socket: {self.path}"
                )
            self.path.unlink()

        config = uvicorn.Config(
            create_mcp_socket_app(),
            uds=str(self.path),
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        self.server = uvicorn.Server(config)
        self.task = asyncio.create_task(self.server.serve())
        for _ in range(100):
            if self.path.is_socket():
                os.chmod(self.path, 0o660)
                socket_stat = self.path.stat()
                self._socket_identity = (socket_stat.st_dev, socket_stat.st_ino)
                if await self._socket_is_healthy():
                    return
            if self.task.done():
                await self.task
            await asyncio.sleep(0.05)
        await self.shutdown()
        raise RuntimeError("Timed out starting the Hermes terminal MCP Unix socket.")

    async def shutdown(self) -> None:
        self._shared_socket = False
        if self.server is not None:
            self.server.should_exit = True
        if self.task is not None:
            try:
                await asyncio.wait_for(self.task, timeout=10)
            except TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
        self._unlink_owned_socket()
        self._release_lock()
        self.server = None
        self.task = None
        self._socket_identity = None

    def _try_acquire_lock(self) -> bool:
        lock_file = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.close()
            return False
        os.chmod(self.lock_path, 0o660)
        self._lock_file = lock_file
        return True

    async def _wait_for_shared_socket_or_lock(self) -> None:
        for _ in range(100):
            if await self._socket_is_healthy():
                self._shared_socket = True
                return
            if self._try_acquire_lock():
                return
            await asyncio.sleep(0.05)
        raise RuntimeError("Timed out waiting for the Hermes terminal MCP Unix socket owner.")

    async def _socket_is_healthy(self) -> bool:
        if not self.path.is_socket():
            return False
        transport = httpx.AsyncHTTPTransport(uds=str(self.path))
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://hermes-terminal-mcp",
                timeout=0.5,
            ) as client:
                response = await client.get("/healthz")
            return response.status_code == 200 and response.json() == {"ready": True}
        except (httpx.HTTPError, OSError, ValueError):
            return False

    def _unlink_owned_socket(self) -> None:
        if self._socket_identity is None:
            return
        try:
            socket_stat = self.path.stat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(socket_stat.st_mode):
            return
        if (socket_stat.st_dev, socket_stat.st_ino) == self._socket_identity:
            self.path.unlink()

    def _release_lock(self) -> None:
        if self._lock_file is None:
            return
        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
        self._lock_file.close()
        self._lock_file = None
