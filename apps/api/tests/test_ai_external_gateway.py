from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_do_api.core.settings import Settings
from ai_do_api.domains.ai import external_gateway
from ai_do_api.domains.ai.external_gateway import (
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    execute_external_capability,
)


def _audit_record_without_detected_values(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "detected_values"}


class _FakeSecurityDb:
    def __init__(self, *, enforcement_enabled: bool) -> None:
        self._enforcement_enabled = enforcement_enabled

    def get(self, model: object, *_args, **_kwargs):
        if getattr(model, "__tablename__", "") == "ai_security_data_protection_settings":
            return SimpleNamespace(enforcement_enabled=self._enforcement_enabled)
        return None


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_execute_external_capability_fails_closed_in_production_like_environment_when_security_is_off(
    monkeypatch,
    environment: str,
) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    monkeypatch.setattr(
        external_gateway,
        "resolve_ai_security_pipeline_exemption",
        lambda *_args, **_kwargs: pytest.fail(
            "production-like enforcement failures must precede exemptions"
        ),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                input_texts=["public launch plan"],
            ),
            _invoke,
            settings=Settings().model_copy(update={"environment": environment}),
            db=_FakeSecurityDb(enforcement_enabled=False),
        )

    assert error.value.reason_code == "ai_security_enforcement_required"
    assert invoked is False
    assert len(records) == 1
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "ai_security_enforcement_required"


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_execute_external_capability_fails_closed_without_security_db_in_production_like_environment(
    monkeypatch,
    environment: str,
) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="image_brief",
                capability="image_brief",
                provider="openai",
                input_texts=["public launch plan"],
            ),
            _invoke,
            settings=Settings().model_copy(update={"environment": environment}),
        )

    assert error.value.reason_code == "ai_security_enforcement_required"
    assert invoked is False
    assert len(records) == 1
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "ai_security_enforcement_required"


def test_execute_external_capability_allows_production_when_security_is_on(
    monkeypatch,
) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    monkeypatch.setattr(
        external_gateway,
        "_evaluate_ai_security_policy",
        lambda *_args, **_kwargs: None,
    )

    def _invoke(execution):
        nonlocal invoked
        invoked = True
        return execution.sanitized_text()

    result = execute_external_capability(
        AiExternalCapabilityRequest(
            source="test.external",
            workspace_id="workspace-1",
            actor_user_id="user-1",
            principal_id="user-1",
            task_kind="web_search",
            capability="web_search",
            provider="anthropic",
            input_texts=["public launch plan"],
        ),
        _invoke,
        settings=Settings().model_copy(update={"environment": "production"}),
        db=_FakeSecurityDb(enforcement_enabled=True),
    )

    assert result == "public launch plan"
    assert invoked is True
    assert len(records) == 1
    assert records[0]["status"] == "ok"
    assert records[0]["policy_reason"] == "allowed"


def test_execute_external_capability_keeps_development_off_compatibility(
    monkeypatch,
) -> None:
    records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    result = execute_external_capability(
        AiExternalCapabilityRequest(
            source="test.external",
            workspace_id="workspace-1",
            actor_user_id="user-1",
            principal_id="user-1",
            task_kind="web_search",
            capability="web_search",
            provider="anthropic",
            input_texts=["public launch plan"],
        ),
        lambda execution: execution.sanitized_text(),
        settings=Settings().model_copy(update={"environment": "development"}),
        db=_FakeSecurityDb(enforcement_enabled=False),
    )

    assert result == "public launch plan"
    assert len(records) == 1
    assert records[0]["status"] == "ok"
    assert records[0]["policy_reason"] == "ai_security_enforcement_disabled"


def test_execute_external_capability_records_success_without_raw_input(monkeypatch) -> None:
    records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    result = execute_external_capability(
        AiExternalCapabilityRequest(
            source="test.external",
            workspace_id="workspace-1",
            actor_user_id="user-1",
            principal_id="user-1",
            task_kind="image_brief",
            capability="image_brief",
            provider="openai",
            input_texts=["public launch plan"],
            entity_id="generation-1",
        ),
        lambda execution: execution.sanitized_text(fallback="fallback"),
        settings=Settings(),
        usage={"input_tokens": 3, "output_tokens": 5},
        metadata={"model": "test-model"},
    )

    assert result == "public launch plan"
    assert len(records) == 1
    assert records[0]["status"] == "ok"
    assert records[0]["provider"] == "openai"
    assert records[0]["policy_reason"] == "allowed"
    assert records[0]["input_text_count"] == 1
    assert records[0]["input_char_count"] == len("public launch plan")
    assert records[0]["usage"] == {"input_tokens": 3, "output_tokens": 5}
    assert records[0]["metadata"] == {"model": "test-model"}
    assert "public launch plan" not in str(records[0])


def test_execute_external_capability_blocks_pii_before_callback(monkeypatch) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                input_texts=["contact owner@example.com"],
            ),
            _invoke,
            settings=Settings(),
        )

    assert error.value.reason_code == "pii_detected"
    assert invoked is False
    assert len(records) == 1
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "pii_detected"
    assert records[0]["pii_hits"] == ["email"]
    assert "owner@example.com" not in str(_audit_record_without_detected_values(records[0]))


def test_execute_external_capability_blocks_overlong_rrn_before_callback(
    monkeypatch,
) -> None:
    records: list[dict] = []
    invoked = False
    blocked_input = "851212-10456712 이지호"
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                input_texts=[blocked_input],
            ),
            _invoke,
            settings=Settings(),
        )

    assert error.value.reason_code == "pii_detected"
    assert invoked is False
    assert len(records) == 1
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "pii_detected"
    assert records[0]["pii_hits"] == ["rrn_kr"]
    assert blocked_input not in str(records[0])


def test_execute_external_capability_blocks_internal_context_before_callback(
    monkeypatch,
) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="image_brief",
                capability="image_brief",
                provider="openai",
                input_texts=["internal deployment evidence"],
                source_kinds=("docs",),
                sensitivity_labels=("internal",),
                content_origin="internal_context",
            ),
            _invoke,
            settings=Settings(),
        )

    assert error.value.reason_code == "internal_context_blocked"
    assert invoked is False
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "internal_context_blocked"
    assert records[0]["content_origin"] == "internal_context"
    assert records[0]["source_kinds"] == ["docs"]
    assert records[0]["sensitivity_labels"] == ["internal"]
    assert "internal deployment evidence" not in str(records[0])


def test_execute_external_capability_blocks_security_document_before_callback(
    monkeypatch,
) -> None:
    records: list[dict] = []
    invoked = False
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )

    def _invoke(_execution):
        nonlocal invoked
        invoked = True
        return "should not run"

    with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
        execute_external_capability(
            AiExternalCapabilityRequest(
                source="test.external",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                input_texts=["보안 문서 VPN 접근 제어 정책 요약"],
            ),
            _invoke,
            settings=Settings(),
        )

    assert error.value.reason_code == "sensitive_entity_blocked"
    assert invoked is False
    assert records[0]["status"] == "blocked"
    assert records[0]["policy_reason"] == "sensitive_entity_blocked"
    assert records[0]["blocked_entity_types"] == ["security_document"]
    assert "보안 문서" not in str(_audit_record_without_detected_values(records[0]))
