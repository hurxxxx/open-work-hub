from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_work_hub_api.domains.agent_terminal.service import (
    AgentTerminalRoot,
    build_codex_environment,
)

_APP_SERVER_TIMEOUT_SECONDS = 10
_APP_SERVER_OUTPUT_LIMIT_BYTES = 1024 * 1024
_MAX_THREAD_ID_LENGTH = 160
_MAX_THREAD_NAME_LENGTH = 240
_MAX_THREAD_PREVIEW_LENGTH = 500


class AgentTerminalCodexHistoryError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _CodexAppServerRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class AgentTerminalCodexThread:
    id: str
    name: str | None
    preview: str | None
    root_key: str
    root_path: str
    created_at: datetime
    updated_at: datetime


class _CodexAppServerConnection:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._request_id = 1

    @classmethod
    async def open(cls, codex_binary: str) -> _CodexAppServerConnection:
        process = await asyncio.create_subprocess_exec(
            codex_binary,
            "app-server",
            "--listen",
            "stdio://",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=build_codex_environment(),
            limit=_APP_SERVER_OUTPUT_LIMIT_BYTES,
        )
        connection = cls(process)
        try:
            await connection.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "open_work_hub",
                        "title": "Open Work Hub",
                        "version": "0.1.1",
                    }
                },
                request_id=0,
            )
            await connection.notify("initialized", {})
            return connection
        except BaseException:
            await connection.close()
            raise

    async def request(
        self,
        method: str,
        params: dict[str, object],
        *,
        request_id: int | None = None,
    ) -> dict[str, Any]:
        current_request_id = self._request_id if request_id is None else request_id
        if request_id is None:
            self._request_id += 1
        await self._send(
            {
                "method": method,
                "id": current_request_id,
                "params": params,
            }
        )
        return await self._read_response(current_request_id)

    async def notify(self, method: str, params: dict[str, object]) -> None:
        await self._send({"method": method, "params": params})

    async def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
            try:
                await self._process.stdin.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
        if self._process.returncode is not None:
            return
        try:
            self._process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=1)
        except TimeoutError:
            self._process.kill()
            await self._process.wait()

    async def _send(self, payload: dict[str, object]) -> None:
        if self._process.stdin is None:
            raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable")
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
        self._process.stdin.write(encoded)
        await self._process.stdin.drain()

    async def _read_response(self, request_id: int) -> dict[str, Any]:
        if self._process.stdout is None:
            raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable")
        while True:
            try:
                line = await self._process.stdout.readline()
            except ValueError as exc:
                raise AgentTerminalCodexHistoryError(
                    "agent_terminal.codex_history_unavailable"
                ) from exc
            if not line or len(line) >= _APP_SERVER_OUTPUT_LIMIT_BYTES:
                raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable")
            try:
                payload = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AgentTerminalCodexHistoryError(
                    "agent_terminal.codex_history_unavailable"
                ) from exc
            if not isinstance(payload, dict) or payload.get("id") != request_id:
                continue
            if payload.get("error") is not None:
                raise _CodexAppServerRequestError
            result = payload.get("result")
            if not isinstance(result, dict):
                raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable")
            return result


async def list_codex_threads(
    *,
    codex_binary: str,
    roots: tuple[AgentTerminalRoot, ...],
    limit: int,
) -> tuple[AgentTerminalCodexThread, ...]:
    if not roots:
        return ()
    connection: _CodexAppServerConnection | None = None
    try:
        async with asyncio.timeout(_APP_SERVER_TIMEOUT_SECONDS):
            connection = await _CodexAppServerConnection.open(codex_binary)
            threads: dict[str, AgentTerminalCodexThread] = {}
            for root in roots:
                result = await connection.request(
                    "thread/list",
                    {
                        "archived": False,
                        "cwd": str(root.path),
                        "limit": limit,
                        "sortDirection": "desc",
                        "sortKey": "updated_at",
                    },
                )
                data = result.get("data")
                if not isinstance(data, list):
                    raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable")
                for item in data:
                    thread = _parse_thread(item, root)
                    if thread is not None:
                        threads[thread.id] = thread
            return tuple(
                sorted(
                    threads.values(),
                    key=lambda thread: thread.updated_at,
                    reverse=True,
                )[:limit]
            )
    except _CodexAppServerRequestError as exc:
        raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable") from exc
    except (OSError, TimeoutError, BrokenPipeError, ConnectionResetError) as exc:
        raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable") from exc
    finally:
        if connection is not None:
            await connection.close()


async def require_codex_thread(
    *,
    codex_binary: str,
    root: AgentTerminalRoot,
    thread_id: str,
) -> AgentTerminalCodexThread:
    connection: _CodexAppServerConnection | None = None
    try:
        async with asyncio.timeout(_APP_SERVER_TIMEOUT_SECONDS):
            connection = await _CodexAppServerConnection.open(codex_binary)
            result = await connection.request(
                "thread/read",
                {"includeTurns": False, "threadId": thread_id},
            )
            thread = _parse_thread(result.get("thread"), root)
            if thread is None or thread.id != thread_id:
                raise AgentTerminalCodexHistoryError("agent_terminal.codex_thread_not_found")
            return thread
    except _CodexAppServerRequestError as exc:
        raise AgentTerminalCodexHistoryError("agent_terminal.codex_thread_not_found") from exc
    except (OSError, TimeoutError, BrokenPipeError, ConnectionResetError) as exc:
        raise AgentTerminalCodexHistoryError("agent_terminal.codex_history_unavailable") from exc
    finally:
        if connection is not None:
            await connection.close()


def _parse_thread(
    value: object,
    root: AgentTerminalRoot,
) -> AgentTerminalCodexThread | None:
    if not isinstance(value, dict):
        return None
    thread_id = value.get("id")
    cwd = value.get("cwd")
    if (
        not isinstance(thread_id, str)
        or not thread_id
        or len(thread_id) > _MAX_THREAD_ID_LENGTH
        or not isinstance(cwd, str)
        or not _same_path(cwd, root.path)
    ):
        return None
    try:
        created_at = _timestamp(value.get("createdAt"))
        updated_at = _timestamp(value.get("updatedAt"))
    except (OverflowError, TypeError, ValueError):
        return None
    name = _display_text(value.get("name"), _MAX_THREAD_NAME_LENGTH)
    preview = _display_text(value.get("preview"), _MAX_THREAD_PREVIEW_LENGTH)
    return AgentTerminalCodexThread(
        id=thread_id,
        name=name,
        preview=preview,
        root_key=root.key,
        root_path=str(root.path),
        created_at=created_at,
        updated_at=updated_at,
    )


def _display_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())[:limit]
    return normalized or None


def _same_path(value: str, root_path: Path) -> bool:
    try:
        return Path(value).expanduser().resolve() == root_path
    except (OSError, RuntimeError):
        return False


def _timestamp(value: object) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError
    return datetime.fromtimestamp(value, tz=UTC)
