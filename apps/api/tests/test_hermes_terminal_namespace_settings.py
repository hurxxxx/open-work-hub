from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_work_hub_api.core import settings as settings_module

NAMESPACE_KEY = "OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.delenv(NAMESPACE_KEY, raising=False)
    monkeypatch.setattr(settings_module, "_settings_env_values", lambda: {})


def _settings(environment, **kwargs):
    return settings_module.Settings(
        _env_file=None,
        postgres_dsn="postgresql+psycopg://test:test@127.0.0.1:1/namespace_test",
        environment=environment,
        seed_dev_login_account=False,
        object_storage_required=True,
        hermes_enabled=False,
        content_grant_signing_key="namespace-test-nondefault-content-signing-key",
        **kwargs,
    )


@pytest.mark.parametrize("environment", ["development", "test"])
def test_local_settings_default_to_development_namespace(environment):
    assert _settings(environment).hermes_terminal_resource_namespace == "dev"


@pytest.mark.parametrize("environment", ["production", "preview"])
@pytest.mark.parametrize(
    "namespace",
    [None, "", "  ", "dev", "local", "Prod", "-prod", "prod/team", "prod_team", "p" * 33],
)
def test_production_settings_reject_missing_invalid_or_development_namespace(
    environment, namespace
):
    extra = {} if namespace is None else {NAMESPACE_KEY: namespace}
    with pytest.raises(ValidationError, match=NAMESPACE_KEY):
        _settings(environment, **extra)


@pytest.mark.parametrize("namespace", ["prod", "company-prod-20260908", "p" * 32])
def test_production_settings_preserve_explicit_resource_boundary(namespace):
    assert (
        _settings("production", **{NAMESPACE_KEY: namespace}).hermes_terminal_resource_namespace
        == namespace
    )


def test_runtime_namespace_uses_typed_environment_alias(monkeypatch):
    monkeypatch.setenv(NAMESPACE_KEY, "company-prod-20260908")
    assert _settings("production").hermes_terminal_resource_namespace == "company-prod-20260908"


def test_invalid_namespace_is_rejected_in_development_too():
    with pytest.raises(ValidationError, match=NAMESPACE_KEY):
        _settings("development", **{NAMESPACE_KEY: "other/resource"})
