from __future__ import annotations

from datetime import datetime, timezone

import importlib.util
from pathlib import Path

import pytest

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelPolicyDefault,
    AiModelProviderConfig,
    AiModelRouteOverride,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    ai_model_registry_digest,
    resolve_ai_model_workload_route,
)
from dev_accounts import auth_headers, dev_login


def admin(client):
    return auth_headers(dev_login(client)["token"])


def seed(db, connection_id, *, kind="openai_compatible", route="local", capabilities=None):
    connection = AiModelProviderConfig(
        provider_id=connection_id,
        provider_kind=kind,
        display_name=connection_id,
        route_mode=route,
        credential_kind="none",
        endpoint_url="http://127.0.0.1:11434/v1",
        enabled=True,
        version=1,
    )
    db.add(connection)
    db.flush()
    model = AiModelCatalogEntry(
        id=f"{connection_id}-model",
        provider_id=connection_id,
        model_key=f"test/{connection_id}",
        display_name=connection_id,
        capabilities_json=capabilities or ["chat", "tool_calling"],
        enabled=True,
        version=1,
    )
    db.add(model)
    db.flush()
    connection.default_model_id = model.id
    return connection, model


def test_global_app_and_workload_inherit_independently_and_shared_workload_is_scoped(client):
    with get_session_factory()() as db:
        a, ma = seed(db, "one")
        b, mb = seed(db, "two")
        db.merge(
            AiModelPolicyDefault(
                app_id="", route_mode="local", provider_id=a.provider_id, max_output_tokens=32768
            )
        )
        db.merge(
            AiModelPolicyDefault(
                app_id="recording",
                route_mode="local",
                provider_id=b.provider_id,
                max_output_tokens=8192,
            )
        )
        db.add(
            AiModelRouteOverride(
                id="meeting-cap",
                app_id="meeting",
                workload_id="meeting_summary",
                local_max_output_tokens=2048,
            )
        )
        db.commit()
        meeting = resolve_ai_model_workload_route(
            db, workload_id="meeting_summary", app_id="meeting"
        )
        recording = resolve_ai_model_workload_route(
            db, workload_id="meeting_summary", app_id="recording"
        )
        assert (meeting.provider_id, meeting.max_output_tokens, meeting.output_cap_source) == (
            "one",
            2048,
            "workload",
        )
        assert (
            recording.provider_id,
            recording.max_output_tokens,
            recording.connection_source,
        ) == ("two", 8192, "app")
        with pytest.raises(AiModelSettingsError, match="workload_app_required"):
            resolve_ai_model_workload_route(db, workload_id="meeting_summary")
        db.get(AiModelPolicyDefault, ("", "local")).provider_id = "two"
        db.flush()
        assert (
            resolve_ai_model_workload_route(
                db, workload_id="meeting_summary", app_id="meeting"
            ).model_key
            == mb.model_key
        )
        assert db.get(AiModelRouteOverride, "meeting-cap").model_ids == {}


@pytest.mark.parametrize("workload_id", ["web_search.answer", "meeting_summary"])
def test_orphaned_overrides_can_be_reset_with_exact_scope_and_version(client, workload_id):
    headers = admin(client)
    with get_session_factory()() as db:
        connection, model = seed(db, "retired")
        connection.default_model_id = None
        model_id = model.id
        db.add(AiModelRouteOverride(
            id="retired-override", app_id="retired-app", workload_id=workload_id,
            model_ids_json={"default": model_id}, version=3,
        ))
        db.add(AiModelRouteOverride(
            id="other-override", app_id="another-retired-app", workload_id=workload_id,
            model_ids_json={}, version=3,
        ))
        db.commit()
    base = "/api/v1/admin/ai-model-settings"
    snapshot = client.get(base, headers=headers).json()
    assert any(row["app_id"] == "retired-app" for row in snapshot["orphaned_overrides"])
    model = next(row for row in snapshot["models"] if row["id"] == model_id)
    update = {
        "expected_registry_digest": snapshot["registry_digest"], "expected_version": model["version"],
        "model_key": model["model_key"], "display_name": model["display_name"],
        "capabilities": model["capabilities"], "enabled": False,
    }
    assert client.put(f"{base}/models/{model_id}", headers=headers, json=update).status_code == 409
    params = {"app_id": "retired-app", "expected_registry_digest": snapshot["registry_digest"], "expected_version": 2}
    path = f"{base}/workloads/{workload_id}/route"
    assert client.delete(path, headers=headers, params=params).status_code == 409
    params["expected_version"] = 3
    response = client.delete(path, headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert all(row["app_id"] != "retired-app" for row in response.json()["orphaned_overrides"])
    with get_session_factory()() as db:
        assert db.get(AiModelRouteOverride, "retired-override") is None
        assert db.get(AiModelRouteOverride, "other-override") is not None
    assert client.delete(path, headers=headers, params=params).status_code == 404
    response = client.put(f"{base}/models/{model_id}", headers=headers, json=update)
    assert response.status_code == 200, response.text


def test_connection_keys_are_encrypted_write_only_preserved_rotated_and_clearable(client):
    headers = admin(client)
    digest = ai_model_registry_digest()
    secret = "synthetic-local-key-only"
    created = client.post(
        "/api/v1/admin/ai-model-settings/connections",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "provider_kind": "openai_compatible",
            "route_mode": "local",
            "preset": "vllm",
            "display_name": "Private GPU",
            "endpoint_url": "http://127.0.0.1:8000/v1",
            "credential_kind": "api_key",
            "api_key": secret,
            "enabled": True,
        },
    )
    assert created.status_code == 201, created.text
    connection = next(
        row for row in created.json()["providers"] if row["display_name"] == "Private GPU"
    )
    assert connection["enabled"] is False
    assert secret not in created.text and connection["has_api_key"]
    identifier = connection["provider_id"]
    with get_session_factory()() as db:
        ciphertext = db.get(AiModelProviderConfig, identifier).api_key_ciphertext
        assert ciphertext != secret and secret not in ciphertext
    for action in ({}, {"api_key": "rotated-synthetic-key"}, {"clear_api_key": True}):
        response = client.put(
            f"/api/v1/admin/ai-model-settings/providers/{identifier}",
            headers=headers,
            json={
                "expected_registry_digest": digest,
                "expected_version": connection["version"],
                "enabled": False,
                "endpoint_url": connection["endpoint_url"],
                **action,
            },
        )
        assert response.status_code == 200, response.text
        connection = next(
            row for row in response.json()["providers"] if row["provider_id"] == identifier
        )
        assert secret not in response.text and "rotated-synthetic-key" not in response.text
        with get_session_factory()() as db:
            current = db.get(AiModelProviderConfig, identifier).api_key_ciphertext
            if not action:
                assert current == ciphertext
            elif "api_key" in action:
                assert current and current != ciphertext
            else:
                assert current is None and not connection["has_api_key"]
    # Same provider family may have independent credentials and identity.
    second = client.post(
        "/api/v1/admin/ai-model-settings/connections",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "provider_kind": "openai_compatible",
            "route_mode": "local",
            "display_name": "Second GPU",
            "credential_kind": "none",
            "endpoint_url": "http://127.0.0.1:8001/v1",
        },
    )
    assert second.status_code == 201
    assert (
        len(
            [
                row
                for row in second.json()["providers"]
                if row["provider_kind"] == "openai_compatible"
            ]
        )
        == 2
    )


def test_default_change_checks_inheriting_workload_capabilities_and_versions(client):
    headers = admin(client)
    with get_session_factory()() as db:
        good, gm = seed(db, "tools")
        bad, bm = seed(db, "chatonly", capabilities=["chat"])
        db.merge(
            AiModelPolicyDefault(
                app_id="", route_mode="local", provider_id=good.provider_id, version=1
            )
        )
        db.commit()
    response = client.put(
        "/api/v1/admin/ai-model-settings/defaults/local",
        headers=headers,
        json={
            "expected_registry_digest": ai_model_registry_digest(),
            "expected_version": 1,
            "provider_id": "chatonly",
            "max_output_tokens": 8192,
        },
    )
    assert (
        response.status_code == 422
        and response.json()["code"] == "admin.ai_model_default_breaks_workload"
    )
    with get_session_factory()() as db:
        assert resolve_ai_model_workload_route(db, workload_id="chatbot").provider_id == "tools"
    conflict = client.put(
        "/api/v1/admin/ai-model-settings/defaults/local",
        headers=headers,
        json={
            "expected_registry_digest": ai_model_registry_digest(),
            "expected_version": 0,
            "provider_id": "tools",
        },
    )
    assert conflict.status_code == 409


def test_runtime_schema_requires_tools_even_when_static_workload_only_requires_chat(client):
    with get_session_factory()() as db:
        connection, _ = seed(db, "plain", capabilities=["chat"])
        db.merge(
            AiModelPolicyDefault(app_id="", route_mode="local", provider_id=connection.provider_id)
        )
        db.commit()
        assert (
            resolve_ai_model_workload_route(db, workload_id="mail_summarize").provider_id == "plain"
        )
        with pytest.raises(AiModelSettingsError, match="capability_mismatch"):
            resolve_ai_model_workload_route(
                db, workload_id="mail_summarize", require_tool_calling=True
            )


def test_env_cutover_preserves_ciphertext_and_unrelated_env_and_is_idempotent(client):
    path = Path(__file__).resolve().parents[3] / "scripts/migrate-llm-settings.py"
    spec = importlib.util.spec_from_file_location("llm_cutover", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = {
        "OPEN_WORK_HUB_LLM_LOCAL_BASE_URL": "http://127.0.0.1:11434/v1",
        "OPEN_WORK_HUB_LLM_LOCAL_API_KEY": "synthetic-only",
    }
    with get_session_factory()() as db:
        keys = module.backfill(db, values)
        db.commit()
        original = db.get(AiModelProviderConfig, "local").api_key_ciphertext
        assert module.backfill(db, values) == keys
        assert db.get(AiModelProviderConfig, "local").api_key_ciphertext == original
        assert db.get(AiModelProviderConfig, "local").credential_kind == "api_key"
    text = "# comment\nOPEN_WORK_HUB_LLM_LOCAL_API_KEY=synthetic-only\nOPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY=preserved\n"
    assert (
        module.prune_keys(text, keys)
        == "# comment\nOPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY=preserved\n"
    )
    with pytest.raises(ValueError):
        module.prune_keys(text + "OTHER=${OPEN_WORK_HUB_LLM_LOCAL_API_KEY}\n", keys)
    for key in ("OPEN_WORK_HUB_LLM_LOCAL_API_KEY", "OPENROUTER_API_KEY"):
        # Refuse before the first DB read/write instead of storing a placeholder.
        with pytest.raises(ValueError, match="referenced LLM settings"):
            module.backfill(None, {key: "${SHARED_PROVIDER_KEY}"})


@pytest.mark.parametrize("missing_endpoint", [None, ""])
def test_env_cutover_requires_explicit_endpoint_for_enabled_legacy_local_connection(
    client, monkeypatch, tmp_path, missing_endpoint
):
    import subprocess

    path = Path(__file__).resolve().parents[3] / "scripts/migrate-llm-settings.py"
    spec = importlib.util.spec_from_file_location("llm_cutover", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".env\n")
    target = tmp_path / ".env"
    original = "OPEN_WORK_HUB_LLM_LOCAL_API_KEY=synthetic-cutover-key\n"
    target.write_text(original)
    target.chmod(0o600)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with get_session_factory()() as db:
        connection, _ = seed(db, "local", kind="local")
        connection.endpoint_url = missing_endpoint
        db.commit()
    with pytest.raises(ValueError, match="explicit endpoint"):
        module.migrate(apply=True)
    assert target.read_text() == original
    assert not list(tmp_path.glob(".env.backup-*"))
    with get_session_factory()() as db:
        connection = db.get(AiModelProviderConfig, "local")
        assert connection.endpoint_url == missing_endpoint
        assert connection.api_key_ciphertext is None

    target.write_text(original + "OPEN_WORK_HUB_LLM_LOCAL_BASE_URL=http://127.0.0.1:8080/v1\n")
    assert module.migrate(apply=True) == {
        "OPEN_WORK_HUB_LLM_LOCAL_API_KEY", "OPEN_WORK_HUB_LLM_LOCAL_BASE_URL"
    }
    with get_session_factory()() as db:
        assert db.get(AiModelProviderConfig, "local").endpoint_url == "http://127.0.0.1:8080/v1"
    assert target.read_text() == ""


@pytest.mark.migration
def test_connection_migration_preserves_keys_and_forks_shared_app_overrides(postgres_dsn):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    import sqlalchemy as sa
    from open_work_hub_api.core.db import Base
    from open_work_hub_api.core.model_registry import import_all_models
    from test_alembic_migrations import _migration_config

    config = _migration_config(postgres_dsn)
    command.upgrade(config, "hermes_initial_snapshot_20260914")
    engine = sa.create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            metadata = sa.MetaData()
            providers = sa.Table("ai_model_provider_configs", metadata, autoload_with=connection)
            overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=connection)
            connection.execute(
                providers.insert().values(
                    provider_id="local",
                    enabled=True,
                    api_key_ciphertext="preserve-ciphertext",
                    version=1,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            connection.execute(
                overrides.insert().values(
                    id="shared-summary",
                    workload_id="meeting_summary",
                    route_mode="local",
                    model_ids_json={},
                    local_max_output_tokens=2048,
                    version=3,
                    created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            connection.execute(overrides.insert().values(
                id="retired-search", workload_id="web_search.answer", route_mode="local",
                model_ids_json={}, version=2,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            ))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT api_key_ciphertext FROM ai_model_provider_configs WHERE provider_id='local'"
                    )
                )
                == "preserve-ciphertext"
            )
            rows = connection.execute(
                sa.text(
                    "SELECT app_id, local_max_output_tokens, version FROM ai_model_route_overrides WHERE workload_id='meeting_summary' ORDER BY app_id"
                )
            ).all()
            assert rows == [("meeting", 2048, 3), ("recording", 2048, 3)]
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT external_max_output_tokens FROM ai_model_route_overrides WHERE workload_id='bento.plan_presentation'"
                    )
                )
                == 16384
            )
            import_all_models()
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        from sqlalchemy.orm import Session
        from open_work_hub_api.domains.ai.model_settings_service import delete_ai_model_route_override

        with Session(engine) as db:
            assert db.get(AiModelRouteOverride, "retired-search").app_id == "web-search"
            delete_ai_model_route_override(
                db, workload_id="web_search.answer", app_id="web-search",
                expected_registry_digest=ai_model_registry_digest(), expected_version=2,
            )
            assert db.get(AiModelRouteOverride, "retired-search") is None
    finally:
        engine.dispose()


def test_saved_connection_probe_releases_db_during_io_and_rejects_concurrent_edits(
    client, monkeypatch
):
    from open_work_hub_api.domains.ai import model_settings_service as service
    from open_work_hub_api.domains.ai.model_discovery import DiscoveredProviderModel

    with get_session_factory()() as db:
        connection, model = seed(db, "probe")
        db.commit()

        def inventory(*_args, **_kwargs):
            assert not db.in_transaction(), "probe must release its DB checkout before provider I/O"
            return (DiscoveredProviderModel("test/probe", "Probe", ("chat", "tool_calling")),)

        monkeypatch.setattr(service, "discover_provider_models", inventory)
        assert service.probe_ai_model_connection(
            db,
            provider_id="probe",
            expected_version=1,
            expected_registry_digest=ai_model_registry_digest(),
        )
        db.commit()
        assert db.get(AiModelProviderConfig, "probe").verified_version == 1

        def changed(*args, **kwargs):
            result = inventory(*args, **kwargs)
            with get_session_factory()() as peer:
                peer.get(AiModelProviderConfig, "probe").version = 2
                peer.commit()
            return result

        monkeypatch.setattr(service, "discover_provider_models", changed)
        with pytest.raises(AiModelSettingsError, match="version_conflict"):
            service.probe_ai_model_connection(
                db,
                provider_id="probe",
                expected_version=1,
                expected_registry_digest=ai_model_registry_digest(),
            )


@pytest.mark.parametrize(
    "endpoint",
    [
        "file:///etc/passwd",
        "http://169.254.169.254/v1",
        "http://unapproved.internal/v1",
        "http://127.0.0.1:bad/v1",
        "http://127.0.0.1/v1?api_key=secret",
    ],
)
def test_connection_endpoint_rejects_untrusted_local_urls(endpoint):
    from open_work_hub_api.domains.ai.model_settings_service import _validate_endpoint_url

    with pytest.raises(AiModelSettingsError):
        _validate_endpoint_url(endpoint, provider_id="example", route_mode="local")


def test_inherited_route_change_rejects_incompatible_model_and_rolls_back(client):
    headers = admin(client)
    with get_session_factory()() as db:
        local, _ = seed(db, "route-local")
        external, _ = seed(
            db, "route-external", kind="openai", route="external", capabilities=["chat"]
        )
        external.endpoint_url = "https://api.openai.com/v1"
        for connection in (local, external):
            db.merge(
                AiModelPolicyDefault(
                    app_id="", route_mode=connection.route_mode, provider_id=connection.provider_id
                )
            )
        db.commit()
    response = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route?app_id=chatbot",
        headers=headers,
        json={
            "expected_registry_digest": ai_model_registry_digest(),
            "expected_version": 0,
            "route_mode": "external",
            "provider_id": None,
        },
    )
    assert response.status_code == 422, response.text
    with get_session_factory()() as db:
        assert resolve_ai_model_workload_route(db, workload_id="chatbot").route == "local"


def test_new_workload_caps_inherit_registration_then_explicit_policy(client, monkeypatch):
    from open_work_hub_api.domains.ai import model_settings_service as service
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry

    registry = AiCapabilityRegistry()
    registry.register_llm_workload(
        workload_id="test.compact",
        task_kind="test_compact",
        owner_domain="ai",
        app_id="chatbot",
        description="Small structured task",
        local_max_output_tokens=1024,
        external_max_output_tokens=2048,
    )
    monkeypatch.setattr(service, "get_ai_capability_registry", lambda: registry)
    with get_session_factory()() as db:
        connection, _ = seed(db, "caps")
        global_default = AiModelPolicyDefault(
            app_id="", route_mode="local", provider_id=connection.provider_id
        )
        db.merge(global_default)
        db.commit()
        result = service.resolve_ai_model_workload_route(db, workload_id="test.compact")
        assert (result.max_output_tokens, result.output_cap_source) == (1024, "registry")
        db.get(AiModelPolicyDefault, ("", "local")).max_output_tokens = 4096
        db.flush()
        result = service.resolve_ai_model_workload_route(db, workload_id="test.compact")
        assert (result.max_output_tokens, result.output_cap_source) == (4096, "global")
        db.add(AiModelPolicyDefault(app_id="chatbot", route_mode="local", max_output_tokens=8192))
        db.flush()
        assert (
            service.resolve_ai_model_workload_route(
                db, workload_id="test.compact"
            ).max_output_tokens
            == 8192
        )
        db.add(
            AiModelRouteOverride(
                id="cap-override",
                app_id="chatbot",
                workload_id="test.compact",
                local_max_output_tokens=2048,
            )
        )
        db.flush()
        assert (
            service.resolve_ai_model_workload_route(
                db, workload_id="test.compact"
            ).max_output_tokens
            == 2048
        )


@pytest.mark.parametrize("edit_during_probe", [False, True])
def test_model_edits_invalidate_saved_and_inflight_connection_probes(
    client, monkeypatch, edit_during_probe
):
    from sqlalchemy import select
    from open_work_hub_api.domains.auth.models import User
    from open_work_hub_api.domains.ai import model_settings_service as service
    from open_work_hub_api.domains.ai.model_discovery import DiscoveredProviderModel
    from open_work_hub_api.domains.ai.model_settings_schemas import AiModelCatalogUpdateRequest

    admin(client)
    with get_session_factory()() as db:
        _, model = seed(db, "model-race")
        model_id, old_key = model.id, model.model_key
        actor = db.scalar(select(User.id))
        db.commit()

        def edit_model():
            with get_session_factory()() as peer:
                current = peer.get(AiModelCatalogEntry, model_id)
                service.update_ai_model_catalog_entry(
                    peer,
                    model_id=model_id,
                    actor_user_id=actor,
                    payload=AiModelCatalogUpdateRequest(
                        expected_registry_digest=ai_model_registry_digest(),
                        expected_version=current.version,
                        model_key="missing-new-model",
                        display_name="Edited",
                        capabilities=["chat", "tool_calling"],
                        enabled=True,
                    ),
                )
                peer.commit()

        def inventory(*_args, **_kwargs):
            if edit_during_probe:
                edit_model()
            return (DiscoveredProviderModel(old_key, "Old", ("chat", "tool_calling")),)

        monkeypatch.setattr(service, "discover_provider_models", inventory)
        if edit_during_probe:
            with pytest.raises(AiModelSettingsError, match="version_conflict"):
                service.probe_ai_model_connection(
                    db,
                    provider_id="model-race",
                    expected_version=1,
                    expected_registry_digest=ai_model_registry_digest(),
                )
            db.rollback()
        else:
            assert service.probe_ai_model_connection(
                db,
                provider_id="model-race",
                expected_version=1,
                expected_registry_digest=ai_model_registry_digest(),
            )
            db.commit()
            edit_model()
        db.expire_all()
        assert db.get(AiModelProviderConfig, "model-race").verified_version is None


def test_runtime_health_preserves_same_family_connections_and_workload_readiness(
    client, monkeypatch
):
    from open_work_hub_api.core.llm import LlmPoolHealth
    from open_work_hub_api.domains.ai import runtime_status, model_settings_service
    from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry

    registry = AiCapabilityRegistry()
    for app in ("chatbot", "mail"):
        registry.register_llm_workload(
            workload_id=f"test.{app}",
            task_kind=f"test_{app}",
            owner_domain="ai",
            app_id=app,
            description="Connection health",
            default_route="external",
        )
    for module in (runtime_status, model_settings_service):
        monkeypatch.setattr(module, "get_ai_capability_registry", lambda: registry)
    monkeypatch.setattr(
        runtime_status,
        "check_resolved_pool_health",
        lambda config, **kwargs: LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.default_model,
            status="ready" if config.connection_id == "healthy" else "not_configured",
        ),
    )
    with get_session_factory()() as db:
        for identifier in ("healthy", "unavailable"):
            connection, _ = seed(db, identifier, kind="openai", route="external")
            connection.endpoint_url = "https://api.openai.com/v1"
        db.merge(AiModelPolicyDefault(app_id="", route_mode="external", provider_id="healthy"))
        db.add(
            AiModelPolicyDefault(app_id="mail", route_mode="external", provider_id="unavailable")
        )
        db.commit()
        result = runtime_status.inspect_registered_llm_runtime(db)
        assert {row.connection_id: row.ready for row in result.pools.external_providers} == {
            "healthy": True,
            "unavailable": False,
        }
        assert result.pools.external.ready is False
        assert {row.task_kind: row.ready for row in result.workloads.tasks} == {
            "test.chatbot": True,
            "test.mail": False,
        }
        assert len(result.pools.public_dict()["connections"]) == 2


@pytest.mark.migration
def test_cap_default_migration_clears_only_untouched_seed_values(postgres_dsn):
    from alembic import command
    import sqlalchemy as sa
    from test_alembic_migrations import _migration_config

    config = _migration_config(postgres_dsn)
    command.upgrade(config, "llm_connections_20260918")
    engine = sa.create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE ai_model_policy_defaults SET version=2 WHERE route_mode='external'")
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            caps = dict(
                connection.execute(
                    sa.text(
                        "SELECT route_mode, max_output_tokens FROM ai_model_policy_defaults WHERE app_id='' "
                    )
                ).all()
            )
            assert caps == {"local": None, "external": 65536}
    finally:
        engine.dispose()


@pytest.mark.parametrize("method", ["delete", "put"])
def test_reset_cannot_break_a_ready_inherited_workload(client, method):
    headers = admin(client)
    with get_session_factory()() as db:
        inherited, _ = seed(db, "inherited-chat-only", capabilities=["chat"])
        explicit, _ = seed(db, "explicit-tools")
        db.merge(
            AiModelPolicyDefault(app_id="", route_mode="local", provider_id=inherited.provider_id)
        )
        db.add(
            AiModelRouteOverride(
                id="working-override",
                app_id="chatbot",
                workload_id="chatbot",
                provider_id=explicit.provider_id,
                version=1,
            )
        )
        db.commit()
    path = "/api/v1/admin/ai-model-settings/workloads/chatbot/route"
    version = {"expected_registry_digest": ai_model_registry_digest(), "expected_version": 1}
    if method == "delete":
        response = client.delete(path, headers=headers, params={"app_id": "chatbot", **version})
    else:
        response = client.put(path + "?app_id=chatbot", headers=headers, json=version)
    assert response.status_code == 422, response.text
    with get_session_factory()() as db:
        assert (
            resolve_ai_model_workload_route(db, workload_id="chatbot").provider_id
            == "explicit-tools"
        )
