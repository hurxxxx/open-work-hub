from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from open_work_hub_api.core.settings import Settings, WORKSPACE_ROOT
from open_work_hub_api.domains.agent_terminal.models import AgentTerminalSession
from open_work_hub_api.domains.agent_terminal.schemas import AgentTerminalSessionResponse


_ROOT_KEY_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_SAFE_ENVIRONMENT_KEYS = (
    "CODEX_HOME",
    "COLORTERM",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_COLOR",
    "PATH",
    "SHELL",
    "USER",
)


class AgentTerminalConfigurationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AgentTerminalRoot:
    key: str
    label: str
    path: Path


def configured_roots(settings: Settings) -> tuple[AgentTerminalRoot, ...]:
    roots: list[AgentTerminalRoot] = []
    for key, configured_path in settings.agent_terminal_allowed_roots.items():
        if not _ROOT_KEY_PATTERN.fullmatch(key):
            raise AgentTerminalConfigurationError("agent_terminal.root_config_invalid")
        candidate = Path(configured_path).expanduser()
        if not candidate.is_absolute():
            candidate = WORKSPACE_ROOT / candidate
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise AgentTerminalConfigurationError("agent_terminal.root_unavailable") from exc
        if not resolved.is_dir():
            raise AgentTerminalConfigurationError("agent_terminal.root_unavailable")
        roots.append(
            AgentTerminalRoot(
                key=key,
                label=key.replace("-", " ").title(),
                path=resolved,
            )
        )
    return tuple(roots)


def resolve_root(settings: Settings, root_key: str) -> AgentTerminalRoot:
    for root in configured_roots(settings):
        if root.key == root_key:
            return root
    raise AgentTerminalConfigurationError("agent_terminal.root_not_found")


def resolve_codex_binary(settings: Settings) -> str | None:
    return _resolve_executable(settings.agent_terminal_codex_bin)


def resolve_tmux_binary(settings: Settings) -> str | None:
    return _resolve_executable(settings.agent_terminal_tmux_bin)


def _resolve_executable(configured: str) -> str | None:
    candidate = shutil.which(configured)
    if candidate is None and Path(configured).is_absolute():
        candidate = configured
    if candidate is None:
        return None
    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        return None
    return str(resolved)


def build_codex_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    inherited = source if source is not None else os.environ
    environment = {key: inherited[key] for key in _SAFE_ENVIRONMENT_KEYS if inherited.get(key)}
    environment["TERM"] = "xterm-256color"
    environment["COLORTERM"] = "truecolor"
    return environment


def serialize_session(row: AgentTerminalSession) -> AgentTerminalSessionResponse:
    return AgentTerminalSessionResponse(
        id=row.id,
        tool="codex",
        root_key=row.root_key,
        root_path=row.root_path,
        status=row.status,  # type: ignore[arg-type]
        exit_code=row.exit_code,
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )
