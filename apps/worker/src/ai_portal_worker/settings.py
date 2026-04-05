from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[4]


WORKSPACE_ROOT = _workspace_root()
ENV_FILES = (
    WORKSPACE_ROOT / ".env.local",
    WORKSPACE_ROOT / ".env",
)


class Settings(BaseSettings):
    broker_url: str = "redis://127.0.0.1:6379/0"
    result_backend: str = "redis://127.0.0.1:6379/1"

    model_config = SettingsConfigDict(
        env_prefix="DOOWON_WORKER_",
        env_file=tuple(str(path) for path in ENV_FILES),
        env_file_encoding="utf-8",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
