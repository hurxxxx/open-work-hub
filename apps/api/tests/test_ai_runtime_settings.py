from __future__ import annotations

from open_work_hub_api.core.settings import Settings


def test_model_status_targets_accept_runtime_env_aliases() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test",
        OPEN_WORK_HUB_MODEL_STATUS_REQUEST_TIMEOUT_SECONDS="7",
        OPEN_WORK_HUB_MODEL_STATUS_DIAGNOSTIC_TARGETS_JSON='[{"id":"replica-a"}]',
    )

    assert settings.model_status_request_timeout_seconds == 7
    assert settings.model_status_diagnostic_targets_json == '[{"id":"replica-a"}]'


def test_phase6_runtime_feature_flags_default_off() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test"
    )

    assert settings.ai_runtime_graph_enabled is False
    assert settings.ai_runtime_graph_execution_enabled is False
    assert settings.ai_runtime_shadow_write_enabled is True
    assert settings.ai_runtime_trace_payload_max_bytes == 32768
    assert settings.ai_runtime_retention_days == 90
    assert settings.ai_tool_calling_enabled is True
    assert settings.ai_local_tool_calling_enabled is False
    assert settings.ai_external_llm_enabled is False
    assert settings.ai_external_planning_enabled is False
    assert settings.ai_external_reasoning_enabled is False
    assert settings.ai_external_quality_review_enabled is False
    assert settings.ai_external_search_enabled is False
    assert settings.ai_external_planner_execution_enabled is False
    assert settings.ai_external_search_execution_enabled is False
    assert settings.ai_external_planner_execution_adapter == "mock"
    assert settings.ai_external_search_execution_adapter == "mock"
    assert settings.ai_default_external_llm_provider == "openai"
    assert settings.ai_default_external_search_provider == "openai"
    assert settings.ai_allowed_external_providers == "openai,anthropic,gemini,kipris"


def test_phase6_runtime_shadow_write_flag_accepts_corporate_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test",
        OPEN_WORK_HUB_AI_RUNTIME_SHADOW_WRITE_ENABLED="0",
    )

    assert settings.ai_runtime_shadow_write_enabled is False


def test_phase6_runtime_trace_payload_cap_accepts_corporate_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test",
        OPEN_WORK_HUB_AI_RUNTIME_TRACE_PAYLOAD_MAX_BYTES="65536",
    )

    assert settings.ai_runtime_trace_payload_max_bytes == 65536


def test_local_tool_calling_flag_accepts_corporate_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test",
        OPEN_WORK_HUB_AI_LOCAL_TOOL_CALLING_ENABLED="1",
    )

    assert settings.ai_local_tool_calling_enabled is True
