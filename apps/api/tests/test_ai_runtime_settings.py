from __future__ import annotations

from aidoo_api.core.settings import Settings


def test_phase6_runtime_feature_flags_default_off() -> None:
    settings = Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test"
    )

    assert settings.ai_runtime_graph_enabled is False
    assert settings.ai_external_llm_enabled is False
    assert settings.ai_external_planning_enabled is False
    assert settings.ai_external_reasoning_enabled is False
    assert settings.ai_external_quality_review_enabled is False
    assert settings.ai_external_search_enabled is False
    assert settings.ai_default_external_search_provider == "openai"
    assert settings.ai_allowed_external_providers == "openai,claude"
