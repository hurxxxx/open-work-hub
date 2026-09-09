from __future__ import annotations

import asyncio
import errno
import fcntl
import hashlib
import os
import pty
import shlex
import signal
import struct
import subprocess
import sys
import termios
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.agent_terminal.models import (
    AgentTerminalSession,
    utcnow_naive,
)
from open_work_hub_api.domains.agent_terminal.service import (
    build_codex_environment,
    resolve_codex_binary,
    resolve_tmux_binary,
)
from open_work_hub_api.domains.auth.access import record_audit_log

_ACTIVE_STATUSES = frozenset({"starting", "running"})
_ATTACHMENT_CHECK_SECONDS = 0.75
_TMUX_COMMAND_TIMEOUT_SECONDS = 5


class AgentTerminalRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _TmuxPaneState:
    dead: bool
    exit_code: int | None
    pid: int | None
    cols: int
    rows: int


@dataclass
class _RuntimeSession:
    session_id: str
    owner_id: str
    process: subprocess.Popen[bytes]
    process_waiter_task: asyncio.Task[int]
    master_fd: int
    replay_limit: int
    replay: bytearray = field(default_factory=bytearray)
    subscribers: set[asyncio.Queue[bytes | None]] = field(default_factory=set)
    reader_task: asyncio.Task[None] | None = None
    monitor_task: asyncio.Task[None] | None = None
    termination_requested: bool = False
    detaching: bool = False
    finished: bool = False
    closed: bool = False
    control_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def append_replay(self, data: bytes) -> None:
        self.replay.extend(data)
        overflow = len(self.replay) - self.replay_limit
        if overflow > 0:
            del self.replay[:overflow]


class AgentTerminalRuntime:
    """Bridges WebSockets to tmux-owned Codex sessions that outlive API workers."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._sessions: dict[str, _RuntimeSession] = {}
        self._lock = asyncio.Lock()
        self._tmux_binary = resolve_tmux_binary(settings)
        socket_identity = ":".join(
            (
                settings.env_profile or settings.environment,
                settings.instance_id,
            )
        )
        socket_digest = hashlib.sha256(socket_identity.encode("utf-8")).hexdigest()[:16]
        self._tmux_socket_name = f"open-work-hub-agent-{socket_digest}"
        self.instance_id = f"{settings.instance_id}:{uuid.uuid4().hex[:12]}"

    async def startup(self) -> None:
        if not self._settings.agent_terminal_enabled or self._tmux_binary is None:
            return
        rows = await asyncio.to_thread(self._load_active_sessions)
        for session_id, owner_id in rows:
            if session_id in self._sessions:
                continue
            pane = await self._inspect_tmux_session(session_id)
            if pane is None:
                await asyncio.to_thread(self._mark_lost, session_id)
                continue
            if pane.dead:
                await asyncio.to_thread(
                    self._mark_finished,
                    session_id,
                    "exited",
                    pane.exit_code,
                )
                continue
            try:
                runtime_session = await self._attach_existing(
                    session_id=session_id,
                    owner_id=owner_id,
                    cols=pane.cols,
                    rows=pane.rows,
                )
            except (AgentTerminalRuntimeError, OSError):
                # The tmux-owned Codex process is still live. Leave the durable row
                # active so a later API restart can attach instead of destroying it.
                continue
            self._sessions[session_id] = runtime_session
            runtime_session.monitor_task = asyncio.create_task(
                self._monitor_session(runtime_session),
                name=f"agent-terminal-monitor:{session_id}",
            )
            await asyncio.to_thread(
                self._mark_recovered,
                session_id,
                pane.pid,
            )

    async def shutdown(self) -> None:
        sessions = tuple(self._sessions.values())
        await asyncio.gather(
            *(self._detach_attachment(session) for session in sessions),
            return_exceptions=True,
        )
        self._sessions.clear()

    async def start(
        self,
        *,
        session_id: str,
        owner_id: str,
        root_path: Path,
        cols: int,
        rows: int,
        codex_thread_id: str | None = None,
    ) -> None:
        if not self._settings.agent_terminal_enabled:
            raise AgentTerminalRuntimeError("agent_terminal.disabled")
        codex_binary = resolve_codex_binary(self._settings)
        if codex_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.codex_unavailable")
        if self._tmux_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.tmux_unavailable")

        async with self._lock:
            self._prune_finished_sessions()
            active_sessions = [
                session for session in self._sessions.values() if not session.finished
            ]
            if len(active_sessions) >= self._settings.agent_terminal_max_sessions_total:
                raise AgentTerminalRuntimeError("agent_terminal.session_limit")
            owner_active_count = sum(session.owner_id == owner_id for session in active_sessions)
            if owner_active_count >= self._settings.agent_terminal_max_sessions_per_user:
                raise AgentTerminalRuntimeError("agent_terminal.session_limit")

            await self._create_tmux_session(
                session_id=session_id,
                root_path=root_path,
                codex_binary=codex_binary,
                cols=cols,
                rows=rows,
                codex_thread_id=codex_thread_id,
            )
            try:
                pane = await self._inspect_tmux_session(session_id)
                if pane is None or pane.dead:
                    raise AgentTerminalRuntimeError("agent_terminal.start_failed")
                runtime_session = await self._attach_existing(
                    session_id=session_id,
                    owner_id=owner_id,
                    cols=pane.cols,
                    rows=pane.rows,
                )
            except BaseException:
                await self._kill_tmux_session(session_id)
                raise
            self._sessions[session_id] = runtime_session
            runtime_session.monitor_task = asyncio.create_task(
                self._monitor_session(runtime_session),
                name=f"agent-terminal-monitor:{session_id}",
            )

        try:
            await asyncio.to_thread(
                self._mark_started,
                session_id,
                pane.pid,
            )
        except Exception as exc:
            await self.terminate(session_id)
            raise AgentTerminalRuntimeError("agent_terminal.start_failed") from exc

    def contains(self, session_id: str) -> bool:
        return session_id in self._sessions

    def is_active(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        return bool(session and not session.finished and not session.detaching)

    def subscribe(
        self,
        session_id: str,
    ) -> tuple[asyncio.Queue[bytes | None], bytes, bool]:
        session = self._sessions.get(session_id)
        if session is None:
            raise AgentTerminalRuntimeError("agent_terminal.session_not_local")
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
        session.subscribers.add(queue)
        return queue, bytes(session.replay), self.is_active(session_id)

    def unsubscribe(
        self,
        session_id: str,
        queue: asyncio.Queue[bytes | None],
    ) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.subscribers.discard(queue)

    def forget(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None and self.is_active(session_id):
            raise AgentTerminalRuntimeError("agent_terminal.session_active")
        self._kill_tmux_session_sync(session_id)
        self._sessions.pop(session_id, None)

    async def write(self, session_id: str, data: bytes) -> None:
        if len(data) > 65_536:
            raise AgentTerminalRuntimeError("agent_terminal.input_too_large")
        session = self._active_session(session_id)
        try:
            await asyncio.to_thread(_write_all, session.master_fd, data)
        except OSError as exc:
            raise AgentTerminalRuntimeError("agent_terminal.session_closed") from exc

    async def scroll(self, session_id: str, *, lines: int) -> None:
        if lines == 0 or abs(lines) > 100:
            raise AgentTerminalRuntimeError("agent_terminal.message_invalid")
        session = self._active_session(session_id)
        target = f"{self._tmux_target(session_id)}:0.0"
        async with session.control_lock:
            copy_return_code, _copy_output = await self._run_tmux(
                "copy-mode",
                "-e",
                "-t",
                target,
            )
            if copy_return_code != 0:
                raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable")
            scroll_return_code, _scroll_output = await self._run_tmux(
                "send-keys",
                "-t",
                target,
                "-X",
                "-N",
                str(abs(lines)),
                "scroll-down" if lines > 0 else "scroll-up",
            )
            if scroll_return_code != 0:
                raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable")

    async def end_scroll(self, session_id: str) -> None:
        session = self._active_session(session_id)
        target = f"{self._tmux_target(session_id)}:0.0"
        async with session.control_lock:
            return_code, _output = await self._run_tmux(
                "send-keys",
                "-t",
                target,
                "-X",
                "cancel",
            )
            if return_code not in {0, 1}:
                raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable")

    async def resize(self, session_id: str, *, cols: int, rows: int) -> None:
        if not 20 <= cols <= 500 or not 5 <= rows <= 200:
            raise AgentTerminalRuntimeError("agent_terminal.size_invalid")
        session = self._active_session(session_id)
        try:
            _set_terminal_size(session.master_fd, cols=cols, rows=rows)
        except OSError as exc:
            raise AgentTerminalRuntimeError("agent_terminal.session_closed") from exc

    async def terminate(self, session_id: str) -> None:
        if self._tmux_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.tmux_unavailable")
        session = self._sessions.get(session_id)
        if session is not None:
            session.termination_requested = True
        await self._kill_tmux_session(session_id)
        if session is not None:
            await self._finish_runtime_session(
                session,
                status="terminated",
                exit_code=0,
            )
        else:
            await asyncio.to_thread(
                self._mark_finished,
                session_id,
                "terminated",
                0,
            )

    def _active_session(self, session_id: str) -> _RuntimeSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise AgentTerminalRuntimeError("agent_terminal.session_not_local")
        if session.finished or session.detaching:
            raise AgentTerminalRuntimeError("agent_terminal.session_closed")
        return session

    def _prune_finished_sessions(self) -> None:
        removable = [
            session
            for session in self._sessions.values()
            if session.finished and not session.subscribers
        ]
        for session in removable[:-50]:
            self._sessions.pop(session.session_id, None)

    async def _create_tmux_session(
        self,
        *,
        session_id: str,
        root_path: Path,
        codex_binary: str,
        cols: int,
        rows: int,
        codex_thread_id: str | None = None,
    ) -> None:
        codex_arguments = [codex_binary]
        if codex_thread_id is not None:
            codex_arguments.append("resume")
        codex_arguments.extend(
            (
                "-C",
                str(root_path),
                "--dangerously-bypass-approvals-and-sandbox",
                "--no-alt-screen",
            )
        )
        if codex_thread_id is not None:
            codex_arguments.append(codex_thread_id)
        command = "exec " + shlex.join(
            (
                sys.executable,
                "-m",
                "open_work_hub_api.domains.agent_terminal.launcher",
                *codex_arguments,
            )
        )
        target = self._tmux_target(session_id)
        return_code, _output = await self._run_tmux(
            "new-session",
            "-d",
            "-s",
            target,
            "-x",
            str(cols),
            "-y",
            str(rows),
            "-c",
            str(root_path),
            command,
            capture_output=False,
        )
        if return_code != 0:
            raise AgentTerminalRuntimeError("agent_terminal.start_failed")
        options = (
            ("set-option", "-t", target, "status", "off"),
            ("set-window-option", "-t", target, "remain-on-exit", "on"),
            ("set-window-option", "-t", target, "window-size", "latest"),
            ("set-window-option", "-t", target, "history-limit", "5000"),
        )
        for arguments in options:
            option_return_code, _option_output = await self._run_tmux(*arguments)
            if option_return_code != 0:
                await self._kill_tmux_session(session_id)
                raise AgentTerminalRuntimeError("agent_terminal.start_failed")

    async def _attach_existing(
        self,
        *,
        session_id: str,
        owner_id: str,
        cols: int,
        rows: int,
    ) -> _RuntimeSession:
        process, master_fd = await self._spawn_attachment(
            session_id=session_id,
            cols=cols,
            rows=rows,
        )
        runtime_session = _RuntimeSession(
            session_id=session_id,
            owner_id=owner_id,
            process=process,
            process_waiter_task=asyncio.create_task(asyncio.to_thread(process.wait)),
            master_fd=master_fd,
            replay_limit=self._settings.agent_terminal_replay_buffer_bytes,
        )
        runtime_session.reader_task = asyncio.create_task(
            self._read_output(runtime_session),
            name=f"agent-terminal-reader:{session_id}",
        )
        return runtime_session

    async def _spawn_attachment(
        self,
        *,
        session_id: str,
        cols: int,
        rows: int,
    ) -> tuple[subprocess.Popen[bytes], int]:
        if self._tmux_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.tmux_unavailable")
        return_code, _output = await self._run_tmux(
            "set-window-option",
            "-t",
            self._tmux_target(session_id),
            "window-size",
            "latest",
        )
        if return_code != 0:
            raise AgentTerminalRuntimeError("agent_terminal.session_not_local")
        master_fd, slave_fd = pty.openpty()
        try:
            _set_terminal_size(slave_fd, cols=cols, rows=rows)
            process = subprocess.Popen(
                (
                    sys.executable,
                    "-m",
                    "open_work_hub_api.domains.agent_terminal.tmux_client_launcher",
                    *self._tmux_prefix(
                        "attach-session",
                        "-t",
                        self._tmux_target(session_id),
                    ),
                ),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=build_codex_environment(),
                close_fds=True,
                start_new_session=True,
            )
        except BaseException:
            os.close(master_fd)
            raise
        finally:
            os.close(slave_fd)
        if process.returncode is not None:
            os.close(master_fd)
            raise AgentTerminalRuntimeError("agent_terminal.session_not_local")
        return process, master_fd

    async def _replace_attachment(
        self,
        session: _RuntimeSession,
        pane: _TmuxPaneState,
    ) -> None:
        self._close_master(session)
        if session.reader_task is not None:
            await asyncio.gather(session.reader_task, return_exceptions=True)
        process, master_fd = await self._spawn_attachment(
            session_id=session.session_id,
            cols=pane.cols,
            rows=pane.rows,
        )
        session.process = process
        session.process_waiter_task = asyncio.create_task(asyncio.to_thread(process.wait))
        session.master_fd = master_fd
        session.closed = False
        session.reader_task = asyncio.create_task(
            self._read_output(session),
            name=f"agent-terminal-reader:{session.session_id}",
        )

    async def _read_output(self, session: _RuntimeSession) -> None:
        while not session.closed:
            try:
                data = await asyncio.to_thread(os.read, session.master_fd, 32_768)
            except OSError as exc:
                if exc.errno in {errno.EBADF, errno.EIO}:
                    return
                raise
            if not data:
                return
            session.append_replay(data)
            for queue in tuple(session.subscribers):
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(data)

    async def _monitor_session(self, session: _RuntimeSession) -> None:
        while not session.detaching and not session.finished:
            await asyncio.wait(
                {session.process_waiter_task},
                timeout=_ATTACHMENT_CHECK_SECONDS,
            )
            if session.detaching or session.finished:
                return
            pane = await self._inspect_tmux_session(session.session_id)
            if pane is not None and not pane.dead:
                if session.process_waiter_task.done():
                    try:
                        await self._replace_attachment(session, pane)
                    except (AgentTerminalRuntimeError, OSError):
                        await asyncio.sleep(_ATTACHMENT_CHECK_SECONDS)
                continue
            status = "terminated" if session.termination_requested else "exited"
            await self._finish_runtime_session(
                session,
                status=status,
                exit_code=pane.exit_code if pane is not None else None,
            )
            return

    async def _finish_runtime_session(
        self,
        session: _RuntimeSession,
        *,
        status: str,
        exit_code: int | None,
    ) -> None:
        if session.finished:
            return
        session.finished = True
        await self._stop_attachment_process(session)
        for queue in tuple(session.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(None)
        await asyncio.to_thread(
            self._mark_finished,
            session.session_id,
            status,
            exit_code,
        )

    async def _detach_attachment(self, session: _RuntimeSession) -> None:
        session.detaching = True
        monitor_task = session.monitor_task
        if monitor_task is not None and monitor_task is not asyncio.current_task():
            monitor_task.cancel()
        await self._stop_attachment_process(session)
        if monitor_task is not None and monitor_task is not asyncio.current_task():
            await asyncio.gather(monitor_task, return_exceptions=True)

    async def _stop_attachment_process(self, session: _RuntimeSession) -> None:
        if session.process.returncode is None:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(
                    asyncio.shield(session.process_waiter_task),
                    timeout=2,
                )
            except TimeoutError:
                try:
                    os.killpg(session.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await session.process_waiter_task
        self._close_master(session)
        if session.reader_task is not None:
            await asyncio.gather(session.reader_task, return_exceptions=True)

    def _close_master(self, session: _RuntimeSession) -> None:
        if session.closed:
            return
        session.closed = True
        try:
            os.close(session.master_fd)
        except OSError:
            pass

    async def _inspect_tmux_session(self, session_id: str) -> _TmuxPaneState | None:
        return_code, output = await self._run_tmux(
            "display-message",
            "-p",
            "-t",
            f"{self._tmux_target(session_id)}:0.0",
            "#{pane_dead}\t#{pane_dead_status}\t#{pane_pid}\t#{pane_width}\t#{pane_height}",
        )
        if return_code != 0:
            return None
        try:
            dead_text, exit_text, pid_text, cols_text, rows_text = (
                output.decode("utf-8").strip().split("\t")
            )
            return _TmuxPaneState(
                dead=dead_text == "1",
                exit_code=int(exit_text) if exit_text else None,
                pid=int(pid_text) if pid_text else None,
                cols=max(20, min(500, int(cols_text))),
                rows=max(5, min(200, int(rows_text))),
            )
        except (UnicodeDecodeError, ValueError) as exc:
            raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable") from exc

    async def _kill_tmux_session(self, session_id: str) -> None:
        return_code, _output = await self._run_tmux(
            "kill-session",
            "-t",
            self._tmux_target(session_id),
        )
        if return_code not in {0, 1}:
            raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable")

    def _kill_tmux_session_sync(self, session_id: str) -> None:
        if self._tmux_binary is None:
            return
        try:
            subprocess.run(
                self._tmux_prefix(
                    "kill-session",
                    "-t",
                    self._tmux_target(session_id),
                ),
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=build_codex_environment(),
                timeout=_TMUX_COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

    async def _run_tmux(
        self,
        *arguments: str,
        capture_output: bool = True,
    ) -> tuple[int, bytes]:
        if self._tmux_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.tmux_unavailable")
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                self._tmux_prefix(*arguments),
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=build_codex_environment(),
                close_fds=True,
                start_new_session=True,
                timeout=_TMUX_COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AgentTerminalRuntimeError("agent_terminal.runtime_unavailable") from exc
        return completed.returncode, completed.stdout or b""

    def _tmux_prefix(self, *arguments: str) -> tuple[str, ...]:
        if self._tmux_binary is None:
            raise AgentTerminalRuntimeError("agent_terminal.tmux_unavailable")
        return (
            self._tmux_binary,
            "-f",
            "/dev/null",
            "-L",
            self._tmux_socket_name,
            *arguments,
        )

    @staticmethod
    def _tmux_target(session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
        return f"owh_{digest}"

    def _load_active_sessions(self) -> tuple[tuple[str, str], ...]:
        with self._session_factory() as db:
            rows = db.execute(
                select(AgentTerminalSession.id, AgentTerminalSession.owner_id).where(
                    AgentTerminalSession.status.in_(_ACTIVE_STATUSES)
                )
            ).all()
        return tuple((session_id, owner_id) for session_id, owner_id in rows)

    def _mark_started(self, session_id: str, pid: int | None) -> None:
        with self._session_factory() as db:
            now = utcnow_naive()
            db.execute(
                update(AgentTerminalSession)
                .where(
                    AgentTerminalSession.id == session_id,
                    AgentTerminalSession.status == "starting",
                )
                .values(
                    status="running",
                    runtime_instance_id=self.instance_id,
                    pid=pid,
                    failure_code=None,
                    started_at=now,
                    updated_at=now,
                )
            )
            db.commit()

    def _mark_recovered(self, session_id: str, pid: int | None) -> None:
        with self._session_factory() as db:
            row = db.get(AgentTerminalSession, session_id)
            if row is None or row.status not in _ACTIVE_STATUSES:
                return
            previous_runtime_instance_id = row.runtime_instance_id
            row.status = "running"
            row.runtime_instance_id = self.instance_id
            row.pid = pid
            row.failure_code = None
            row.updated_at = utcnow_naive()
            record_audit_log(
                db,
                action="agent_terminal.session.recover",
                entity_kind="agent_terminal_session",
                entity_id=row.id,
                summary="Reattached tmux-owned Codex terminal session",
                payload={
                    "previous_runtime_instance_id": previous_runtime_instance_id,
                    "runtime_instance_id": self.instance_id,
                },
            )
            db.commit()

    def _mark_lost(self, session_id: str) -> None:
        with self._session_factory() as db:
            row = db.get(AgentTerminalSession, session_id)
            if row is None or row.status not in _ACTIVE_STATUSES:
                return
            previous_status = row.status
            now = utcnow_naive()
            row.status = "failed"
            row.failure_code = "agent_terminal.tmux_session_lost"
            row.ended_at = now
            row.updated_at = now
            record_audit_log(
                db,
                action="agent_terminal.session.finish",
                entity_kind="agent_terminal_session",
                entity_id=row.id,
                summary="Could not recover tmux-owned Codex terminal session",
                payload={
                    "status": "failed",
                    "previous_status": previous_status,
                    "failure_code": row.failure_code,
                },
            )
            db.commit()

    def _mark_finished(
        self,
        session_id: str,
        status: str,
        exit_code: int | None,
    ) -> None:
        with self._session_factory() as db:
            row = db.get(AgentTerminalSession, session_id)
            if row is None or row.status not in _ACTIVE_STATUSES:
                return
            now = utcnow_naive()
            row.status = status
            row.exit_code = exit_code
            row.ended_at = now
            row.updated_at = now
            record_audit_log(
                db,
                actor_user_id=row.owner_id,
                action="agent_terminal.session.finish",
                entity_kind="agent_terminal_session",
                entity_id=session_id,
                summary="Finished Codex terminal session",
                payload={"status": status, "exit_code": exit_code},
            )
            db.commit()


def _set_terminal_size(fd: int, *, cols: int, rows: int) -> None:
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _write_all(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(fd, remaining)
        remaining = remaining[written:]
