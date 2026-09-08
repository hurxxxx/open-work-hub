from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_work_hub_api.core.settings import DEFAULT_CONTENT_GRANT_SIGNING_KEY, Settings

POSTGRES_DSN = "postgresql+psycopg://test:test@127.0.0.1:5432/test"


@pytest.fixture(autouse=True)
def isolated_shared_signing_setting(monkeypatch):
    monkeypatch.delenv("OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY", raising=False)
    monkeypatch.setenv("OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT", "0")
    monkeypatch.setenv("OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED", "1")


def test_dm_content_uses_shared_grants_without_a_dedicated_public_signing_setting():
    assert "dm_attachment_signing_key" not in Settings.model_fields
    assert (
        Settings(_env_file=None, postgres_dsn=POSTGRES_DSN).content_grant_signing_key
        == DEFAULT_CONTENT_GRANT_SIGNING_KEY
    )


def test_shared_content_signing_key_uses_its_typed_environment_alias():
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY="unit-test-content-signing-key",
    )
    assert settings.content_grant_signing_key == "unit-test-content-signing-key"


@pytest.mark.parametrize("environment", ["production", "preview"])
@pytest.mark.parametrize(
    "key",
    [
        None,
        "",
        "  ",
        DEFAULT_CONTENT_GRANT_SIGNING_KEY,
        "short",
        "a" * 31,
        "development-" + "a" * 32,
        "CHANGE_ME-" + "a" * 32,
    ],
)
def test_shared_content_grants_reject_missing_or_default_signing_key_in_production_like_environments(
    environment, key
):
    extra = {} if key is None else {"content_grant_signing_key": key}
    with pytest.raises(ValidationError, match="OPEN_WORK_HUB_CONTENT_GRANT_SIGNING_KEY"):
        Settings(_env_file=None, postgres_dsn=POSTGRES_DSN, environment=environment, **extra)


@pytest.mark.parametrize("environment", ["production", "preview"])
def test_shared_content_grants_accept_explicit_production_like_signing_key(environment):
    settings = Settings(
        _env_file=None,
        postgres_dsn=POSTGRES_DSN,
        environment=environment,
        content_grant_signing_key="unit-test-nondefault-content-signing-key",
        hermes_terminal_resource_namespace="production-content-grant-test",
    )
    assert settings.content_grant_signing_key == "unit-test-nondefault-content-signing-key"
