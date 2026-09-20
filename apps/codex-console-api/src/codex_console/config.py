import re
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from .errors import ConsoleError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_DATABASE_URL")
    origin: str = Field(validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_ORIGIN")
    base_path: str = Field(default="", validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_BASE_PATH")
    workspace: Path = Field(validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_WORKSPACE")
    worktree_base_ref: str = Field(
        default="HEAD",
        min_length=1,
        max_length=1024,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_WORKTREE_BASE_REF",
    )
    worktree_root: Path = Field(
        default_factory=lambda: Path.home() / ".local/share/owh-codex-console/worktrees",
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_WORKTREE_ROOT",
    )
    protected_workspaces: list[Path] = Field(
        default_factory=list,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_PROTECTED_WORKSPACES",
    )
    forbidden_database_names: list[str] = Field(
        default_factory=list,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_FORBIDDEN_DATABASE_NAMES",
    )
    binary: str = Field(default="codex", validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_BINARY")
    allowed_reasoning_efforts: list[
        Annotated[str, Field(min_length=1, max_length=40, pattern=r"^\S+$")]
    ] = Field(
        default_factory=lambda: ["none", "minimal", "low", "medium", "high", "xhigh"],
        min_length=1,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_ALLOWED_REASONING_EFFORTS",
    )
    bind_host: str = Field(
        default="127.0.0.1", validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_BIND_HOST"
    )
    port: int = Field(
        default=19365, ge=1024, le=65535, validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_PORT"
    )
    web_dist: Path = Field(
        default=Path("../codex-console-web/dist"),
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_WEB_DIST",
    )
    session_hours: int = Field(
        default=12, ge=1, le=24, validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_SESSION_HOURS"
    )
    attachment_cache: Path = Field(
        default_factory=lambda: Path.home() / ".local/share/owh-codex-console/attachments",
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_CACHE",
    )
    attachment_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_MAX_BYTES",
    )
    attachment_task_max_bytes: int = Field(
        default=500 * 1024 * 1024,
        ge=1,
        le=10 * 1024 * 1024 * 1024,
        validation_alias="OPEN_WORK_HUB_CODEX_CONSOLE_ATTACHMENT_TASK_MAX_BYTES",
    )

    @field_validator("attachment_cache")
    @classmethod
    def absolute_attachment_cache(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("Attachment cache must be absolute")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername != "postgresql+psycopg" or not url.database:
            raise ValueError("A dedicated PostgreSQL database with psycopg is required")
        return value

    @field_validator("origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.username
            or not parsed.hostname
        ):
            raise ValueError("Expected an origin without a path or credentials")
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in ("127.0.0.1", "localhost", "[::1]", "::1")
        ):
            raise ValueError("HTTPS is required except for local development")
        return value.rstrip("/")

    @field_validator("workspace")
    @classmethod
    def absolute_workspace(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Workspace must be absolute")
        resolved = value.resolve(strict=True)
        if not (resolved / ".git").exists():
            raise ValueError("Workspace must be a Git checkout")
        return resolved

    @model_validator(mode="after")
    def protected_locations(self):
        if not self.worktree_root.expanduser().is_absolute():
            raise ValueError("Worktree storage must be absolute")
        self.worktree_root = self.worktree_root.expanduser().resolve()
        if self.worktree_root.is_relative_to(self.workspace):
            raise ValueError("Worktree storage must be outside the configured checkout")
        for path in self.protected_workspaces:
            if not path.expanduser().is_absolute():
                raise ValueError("Protected workspaces must be absolute")
            protected = path.expanduser().resolve()
            if self.workspace.is_relative_to(protected) or self.worktree_root.is_relative_to(
                protected
            ):
                raise ValueError("A protected workspace cannot be used by the console")
        if make_url(self.database_url).database in self.forbidden_database_names:
            raise ValueError("The console requires its dedicated database")
        return self

    def require_allowed_paths(self, *paths):
        """Apply current protection settings to persisted and resolved execution paths."""
        protected = [path.expanduser().resolve() for path in self.protected_workspaces]
        for value in paths:
            if value is None:
                continue
            path = Path(value).expanduser()
            if not path.is_absolute() or any(
                path.resolve().is_relative_to(root) for root in protected
            ):
                raise ConsoleError("path_denied", 403)

    @field_validator("base_path")
    @classmethod
    def validate_base_path(cls, value: str) -> str:
        if value and not re.fullmatch(r"(?:/[a-zA-Z0-9_-]+)+", value):
            raise ValueError("Base path must be empty or an absolute path without a trailing slash")
        return value

    @field_validator("bind_host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if value not in ("127.0.0.1", "::1"):
            raise ValueError("Bind to loopback and expose the console through a TLS reverse proxy")
        return value

    @property
    def secure_cookies(self) -> bool:
        return self.origin.startswith("https://")
