from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_do_api.core.settings import DEFAULT_DM_ATTACHMENT_SIGNING_KEY, Settings


POSTGRES_DSN = "postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test"


@pytest.fixture(autouse=True)
def clear_dm_attachment_signing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_DO_DM_ATTACHMENT_SIGNING_KEY", raising=False)
    monkeypatch.delenv("AI_DO_API_DM_ATTACHMENT_SIGNING_KEY", raising=False)


def test_dm_attachment_signing_key_defaults_for_development() -> None:
    settings = Settings(_env_file=None, postgres_dsn=POSTGRES_DSN)

    assert settings.dm_attachment_signing_key == DEFAULT_DM_ATTACHMENT_SIGNING_KEY


def test_dm_attachment_signing_key_accepts_legacy_alias() -> None:
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        AI_DO_DM_ATTACHMENT_SIGNING_KEY="custom-signing-secret",
    )

    assert settings.dm_attachment_signing_key == "custom-signing-secret"


def test_dm_attachment_signing_key_rejects_default_in_production() -> None:
    with pytest.raises(ValidationError, match="AI_DO_DM_ATTACHMENT_SIGNING_KEY"):
        Settings(
            _env_file=None,
            postgres_dsn=POSTGRES_DSN,
            environment="production",
        )


def test_dm_attachment_signing_key_is_required_in_production() -> None:
    with pytest.raises(ValidationError, match="AI_DO_DM_ATTACHMENT_SIGNING_KEY"):
        Settings(
            _env_file=None,
            postgres_dsn=POSTGRES_DSN,
            environment="production",
            dm_attachment_signing_key=" ",
        )


def test_dm_attachment_signing_key_rejects_default_in_preview() -> None:
    with pytest.raises(ValidationError, match="AI_DO_DM_ATTACHMENT_SIGNING_KEY"):
        Settings(
            _env_file=None,
            postgres_dsn=POSTGRES_DSN,
            environment="preview",
        )


def test_dm_attachment_signing_key_accepts_custom_production_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        environment="production",
        dm_attachment_signing_key="production-signing-secret",
    )

    assert settings.dm_attachment_signing_key == "production-signing-secret"


def test_dm_attachment_signing_key_accepts_custom_preview_secret() -> None:
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        environment="preview",
        dm_attachment_signing_key="preview-signing-secret",
    )

    assert settings.environment == "preview"
    assert settings.dm_attachment_signing_key == "preview-signing-secret"
