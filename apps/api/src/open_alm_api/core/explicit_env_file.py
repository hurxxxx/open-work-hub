from __future__ import annotations

from collections.abc import Collection
from pathlib import Path
import re

from dotenv.parser import parse_stream


_ENV_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ExplicitEnvFileError(RuntimeError):
    """Raised when an explicitly requested environment file cannot be loaded."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def load_explicit_env_file(
    path: Path,
    *,
    allowed_keys: Collection[str],
) -> dict[str, str]:
    """Read an explicit dotenv file and return only allowlisted values."""

    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise ExplicitEnvFileError("env_file_unavailable") from exc
    if not resolved.is_file():
        raise ExplicitEnvFileError("env_file_unavailable")

    try:
        with resolved.open(encoding="utf-8") as stream:
            bindings = tuple(parse_stream(stream))
    except (OSError, UnicodeError) as exc:
        raise ExplicitEnvFileError("env_file_invalid") from exc

    values: dict[str, str] = {}
    seen: set[str] = set()
    for binding in bindings:
        if binding.error:
            raise ExplicitEnvFileError("env_file_invalid")
        key = binding.key
        if key is None:
            continue
        if not _ENV_KEY_PATTERN.fullmatch(key):
            raise ExplicitEnvFileError("env_file_invalid")
        if key in seen:
            raise ExplicitEnvFileError("env_file_duplicate_key")
        seen.add(key)
        if key in allowed_keys:
            values[key] = binding.value or ""
    return values


__all__ = ["ExplicitEnvFileError", "load_explicit_env_file"]
