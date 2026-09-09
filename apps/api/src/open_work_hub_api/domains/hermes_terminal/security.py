from __future__ import annotations

import hashlib
import hmac
from pathlib import PurePosixPath

from open_work_hub_api.core.settings import Settings


def broker_bearer_token(settings: Settings) -> str:
    root_secret = settings.hermes_mcp_shared_secret.get_secret_value()
    if not root_secret:
        return ""
    return hmac.new(
        root_secret.encode(),
        b"open-work-hub-hermes-terminal-broker:v1",
        hashlib.sha256,
    ).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def terminal_profile_name(profile_binding_id: str) -> str:
    digest = hashlib.sha256(profile_binding_id.encode()).hexdigest()[:32]
    return f"owhterm{digest}"


def normalize_relative_path(value: str | None, *, allow_root: bool = True) -> str:
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
