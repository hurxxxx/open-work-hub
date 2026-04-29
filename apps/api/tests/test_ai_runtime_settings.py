from __future__ import annotations

from aidoo_api.core.settings import Settings


def test_phase6_runtime_feature_flags_default_off() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test"
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
    assert settings.ai_default_external_search_provider == "openai"
    assert settings.ai_allowed_external_providers == "openai,claude"


def test_phase6_runtime_shadow_write_flag_accepts_doowon_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        DOOWON_API_AIDOO_AI_RUNTIME_SHADOW_WRITE_ENABLED="0",
    )

    assert settings.ai_runtime_shadow_write_enabled is False


def test_phase6_runtime_trace_payload_cap_accepts_doowon_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        DOOWON_API_AIDOO_AI_RUNTIME_TRACE_PAYLOAD_MAX_BYTES="65536",
    )

    assert settings.ai_runtime_trace_payload_max_bytes == 65536


def test_local_tool_calling_flag_accepts_doowon_api_alias() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        DOOWON_API_AIDOO_AI_LOCAL_TOOL_CALLING_ENABLED="1",
    )

    assert settings.ai_local_tool_calling_enabled is True
