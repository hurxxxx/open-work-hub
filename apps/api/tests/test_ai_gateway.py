from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from open_work_hub_api.core.llm import LlmPoolConfig
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai import audit as audit_module
from open_work_hub_api.domains.ai import gateway as gateway_module
from open_work_hub_api.domains.ai import masking as masking_module
from open_work_hub_api.domains.ai.gateway import (
    AiGatewayContextPack,
    AiGatewayPolicyViolation,
    AiGatewayRequest,
    LlmWorkloadContext,
    complete_gateway_chat,
    execute_llm,
    resolve_gateway_execution,
)
from open_work_hub_api.domains.ai.privacy_filter import PrivacyFilterDetection, PrivacyFilterSpan
from open_work_hub_api.domains.ai.registry import (
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from open_work_hub_api.domains.ai.security_policy import (
    POLICY_MASK_AND_SEND_REASON,
    AiSecurityPolicyDecision,
)


class _FakeSecuritySettings:
    def __init__(self, enabled: bool) -> None:
        self.enforcement_enabled = enabled
        self.enforcement_disabled_reason = ""
        self.custom_block_terms_json: list[str] = []
        self.blocker_actions_json: dict[str, str] = {}
        self.external_app_actions_json: dict[str, dict[str, str]] = {}


class _FakePolicyDb:
    def __init__(self, policy: str | None, *, ai_security_enabled: bool = True) -> None:
        self._policy = policy
        self._ai_security_enabled = ai_security_enabled

    def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        policy = self._policy

        class _Result:
            def scalar_one_or_none(self) -> str | None:
                return policy

        return _Result()

    def get(self, model: object, *_args: Any, **_kwargs: Any) -> Any:
        if getattr(model, "__tablename__", "") == "ai_security_data_protection_settings":
            return _FakeSecuritySettings(self._ai_security_enabled)
        return None

    def scalar(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def scalars(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def all(self) -> list[Any]:
                return []

        return _Result()


def _request(task_kind: str, **overrides: Any) -> AiGatewayRequest:
    registry = get_ai_capability_registry()
    workload = registry.get_llm_workload(task_kind)
    if workload is None:
        workload = registry.resolve_llm_workload_for_task(
            app_id="files",
            task_kind=task_kind,
        )
    route = overrides.pop(
        "workload_route",
        "external" if task_kind == "files_grounded_chat" else "local",
    )
    config = LlmPoolConfig(
        pool=route,
        provider="anthropic" if route == "external" else "vllm",
        base_url=("https://api.anthropic.com" if route == "external" else "http://local.test/v1"),
        api_key="test-key",
        default_model="test-model",
        canonical_model="test-model",
        healthcheck_timeout_seconds=1.0,
        long_generation_timeout_seconds=30.0,
    )
    values: dict[str, Any] = {
        "task_kind": task_kind,
        "workload_id": workload.workload_id if workload is not None else None,
        "workload_route": route if workload is not None else None,
        "workload_config": config if workload is not None else None,
        "workload_local_max_output_tokens": 32_768,
        "workload_external_max_output_tokens": 65_536,
        "actor_user_id": "user-1",
        "source": "tests.ai_gateway",
        "app": workload.app_id if workload is not None else "chatbot",
        "requested_model": "test-model" if workload is not None else None,
        "requested_provider": "anthropic" if route == "external" else None,
        "max_tokens": 65_536 if route == "external" else 32_768,
        "messages": [{"role": "user", "content": "hello"}],
    }
    values.update(overrides)
    return AiGatewayRequest(**values)


def test_chatbot_task_is_registered_with_default_budgets() -> None:
    reset_ai_capability_registry()
    try:
        registry = get_ai_capability_registry()

        workload = registry.resolve_llm_workload("chatbot")

        assert "chatbot" in registry.llm_tasks
        assert workload.local_max_output_tokens == 32_768
        assert workload.external_max_output_tokens == 65_536
    finally:
        reset_ai_capability_registry()


def test_common_completion_executes_hermes_instead_of_provider_sdk(monkeypatch):
    from open_work_hub_api.domains.hermes import workloads

    calls = []

    def complete(context, execution, payload, **kwargs):
        calls.append((context, execution, payload, kwargs))
        return {
            "choices": [{"message": {"content": "validated"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "structured_output": {"answer": 42},
        }

    monkeypatch.setattr(workloads, "complete_workload", complete)
    monkeypatch.setattr(gateway_module, "log_llm_call", lambda **kwargs: None)
    request = _request("chatbot", output_schema={"type": "object"})
    result = complete_gateway_chat(request, _FakePolicyDb("local"))
    assert len(calls) == 1
    assert calls[0][0].workload_id == "chatbot"
    assert calls[0][1].pool == "local"
    assert calls[0][3]["output_schema"] == {"type": "object"}
    assert result.response["structured_output"] == {"answer": 42}


def test_gateway_request_requires_app_id() -> None:
    with pytest.raises(ValueError, match="LLM app_id is required"):
        _request("chatbot", app=None)


def test_gateway_unknown_task_kind_does_not_route_external() -> None:
    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(_request("unknown_gateway_task"), _FakePolicyDb("external"))
    assert exc_info.value.reason_code == "unknown_task_kind_local_only"


def test_registered_external_provider_is_blocked_by_egress_allowlist_even_when_security_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS", "openai")
    get_settings.cache_clear()
    try:
        with pytest.raises(AiGatewayPolicyViolation) as exc_info:
            resolve_gateway_execution(
                _request("files_grounded_chat", requested_provider="anthropic"),
                _FakePolicyDb("external", ai_security_enabled=False),
            )
    finally:
        get_settings.cache_clear()

    assert exc_info.value.reason_code == "provider_not_allowed"


def test_gateway_uses_registry_default_policy_for_local_only_tasks() -> None:
    execution = resolve_gateway_execution(
        _request("chatbot"),
        _FakePolicyDb("external"),
    )

    assert execution.decision.chosen_pool == "local"
    assert execution.decision.policy == "local_only"
    assert execution.decision.forced_local is False
    assert execution.llm_execution.decision.reason == "workload_route"


def test_gateway_clamps_to_cap_for_actual_policy_selected_route() -> None:
    execution = resolve_gateway_execution(
        _request(
            "chatbot",
            max_tokens=65_536,
            workload_local_max_output_tokens=16_384,
            workload_external_max_output_tokens=65_536,
        ),
        _FakePolicyDb("external"),
    )

    assert execution.decision.chosen_pool == "local"
    assert execution.llm_execution.resolved_max_tokens == 16_384
    assert execution.decision.max_tokens == 16_384


def test_gateway_preserves_explicit_local_pool_hint_for_local_only_tasks() -> None:
    execution = resolve_gateway_execution(
        _request("chatbot", pool_hint="local"),
        _FakePolicyDb("external"),
    )

    assert execution.decision.chosen_pool == "local"
    assert execution.decision.policy == "local_only"
    assert execution.decision.forced_local is False


def test_gateway_ignores_explicit_provider_for_registered_local_route() -> None:
    execution = resolve_gateway_execution(
        _request("chatbot", requested_provider="openai"),
        _FakePolicyDb("external"),
    )
    assert execution.decision.chosen_pool == "local"
    assert execution.decision.provider == "vllm"


def test_gateway_forces_local_for_internal_context_pack_on_external_policy() -> None:
    context_pack = AiGatewayContextPack(
        messages=[{"role": "user", "content": "server-built evidence"}],
        context_strategy="domain_context_pack",
        source_kinds=("docs",),
        sensitivity_labels=("internal",),
        content_origin="internal_context",
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request("files_grounded_chat", context_pack=context_pack),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_context_pack_without_provenance_fails_closed() -> None:
    context_pack = AiGatewayContextPack(
        messages=[{"role": "user", "content": "server-built evidence"}],
        context_strategy="domain_context_pack",
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request("files_grounded_chat", context_pack=context_pack),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_rejects_requested_provider_for_internal_context_pack() -> None:
    context_pack = AiGatewayContextPack(
        messages=[{"role": "user", "content": "server-built evidence"}],
        context_strategy="domain_context_pack",
        source_kinds=("docs",),
        sensitivity_labels=("internal",),
        content_origin="internal_context",
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                context_pack=context_pack,
                requested_provider="openai",
            ),
            _FakePolicyDb("external"),
        )

    assert exc_info.value.reason_code == "external_transfer_blocked"
    assert exc_info.value.task_kind == "files_grounded_chat"
    assert exc_info.value.requested_provider == "openai"


def test_gateway_forces_local_for_security_document_prompt() -> None:
    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "보안 문서 VPN 접근 제어 정책 요약"}],
            ),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_audits_external_block_without_invoking_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records: list[dict[str, Any]] = []
    monkeypatch.setattr(gateway_module, "log_llm_call", lambda **kwargs: records.append(kwargs))

    with pytest.raises(AiGatewayPolicyViolation):
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "Contact owner@example.com"}],
            ),
            _FakePolicyDb("external"),
        )

    assert len(records) == 1
    assert records[0]["status"] == "blocked_external"
    assert records[0]["chosen_pool"] == "external"
    assert records[0]["decision_reason"] == "external_transfer_blocked"


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_gateway_fails_closed_before_provider_in_production_like_environment_when_security_is_off(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    records: list[dict[str, Any]] = []
    invoked = False
    production_settings = get_settings().model_copy(update={"environment": environment})
    monkeypatch.setattr(gateway_module, "get_settings", lambda: production_settings)
    monkeypatch.setattr(
        gateway_module,
        "log_llm_call",
        lambda **kwargs: records.append(kwargs),
    )
    monkeypatch.setattr(
        gateway_module,
        "resolve_ai_security_pipeline_exemption",
        lambda *_args, **_kwargs: pytest.fail(
            "production-like enforcement failures must precede exemptions"
        ),
    )

    def fake_complete_chat(*_args: Any, **kwargs: Any) -> tuple[object, object, object]:
        nonlocal invoked
        invoked = True
        execution = kwargs["resolved_execution"]
        return object(), execution.decision, execution.config

    monkeypatch.setattr(gateway_module, "_complete_chat", fake_complete_chat)

    with pytest.raises(AiGatewayPolicyViolation) as error:
        complete_gateway_chat(
            _request("files_grounded_chat"),
            _FakePolicyDb("external", ai_security_enabled=False),
        )

    assert error.value.reason_code == "ai_security_enforcement_required"
    assert invoked is False
    assert len(records) == 1
    assert records[0]["status"] == "blocked_external"
    assert records[0]["decision_reason"] == "ai_security_enforcement_required"


def test_gateway_allows_provider_execution_in_production_when_security_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invoked = False
    production_settings = get_settings().model_copy(update={"environment": "production"})
    monkeypatch.setattr(gateway_module, "get_settings", lambda: production_settings)

    def fake_complete_chat(*_args: Any, **kwargs: Any) -> tuple[object, object, object]:
        nonlocal invoked
        invoked = True
        execution = kwargs["resolved_execution"]
        return object(), execution.decision, execution.config

    monkeypatch.setattr(gateway_module, "_complete_chat", fake_complete_chat)

    result = complete_gateway_chat(
        _request("files_grounded_chat"),
        _FakePolicyDb("external", ai_security_enabled=True),
    )

    assert invoked is True
    assert result.decision.chosen_pool == "external"


def test_gateway_keeps_external_route_in_development_when_security_enforcement_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    development_settings = get_settings().model_copy(update={"environment": "development"})
    monkeypatch.setattr(gateway_module, "get_settings", lambda: development_settings)

    execution = resolve_gateway_execution(
        _request(
            "files_grounded_chat",
            messages=[{"role": "user", "content": "Contact owner@example.com"}],
        ),
        _FakePolicyDb("external", ai_security_enabled=False),
    )

    assert execution.decision.chosen_pool == "external"
    assert execution.decision.forced_local is False
    assert execution.decision.reason_codes == ("ai_security_enforcement_disabled",)
    assert execution.decision.pii_hits == ()
    assert execution.detected_values == ()


def test_gateway_keeps_local_route_in_production_when_security_enforcement_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production_settings = get_settings().model_copy(update={"environment": "production"})
    monkeypatch.setattr(gateway_module, "get_settings", lambda: production_settings)

    execution = resolve_gateway_execution(
        _request("chatbot"),
        _FakePolicyDb("local", ai_security_enabled=False),
    )

    assert execution.decision.chosen_pool == "local"
    assert execution.decision.reason_codes == ("workload_route",)


def test_gateway_mask_and_send_masks_regex_pii_before_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "evaluate_ai_security_policy",
        lambda *_args, **_kwargs: AiSecurityPolicyDecision(
            effect="mask_and_send",
            reason_code=POLICY_MASK_AND_SEND_REASON,
        ),
    )
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )

    execution = resolve_gateway_execution(
        _request(
            "files_grounded_chat",
            messages=[{"role": "user", "content": "Contact owner@example.com for review"}],
        ),
        _FakePolicyDb("external"),
    )

    assert execution.decision.chosen_pool == "external"
    assert execution.decision.mask_applied is True
    assert execution.decision.privacy_filter_status == "ok"
    assert "pii:email" in execution.decision.masked_entity_types
    assert "owner@example.com" not in str(execution.messages)
    assert "[masked:pii]" in execution.messages[0]["content"]
    assert execution.decision.reason_codes == (
        "external_payload_masked",
        POLICY_MASK_AND_SEND_REASON,
    )


def test_gateway_mask_and_send_hard_blocks_privacy_filter_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "evaluate_ai_security_policy",
        lambda *_args, **_kwargs: AiSecurityPolicyDecision(
            effect="mask_and_send",
            reason_code=POLICY_MASK_AND_SEND_REASON,
        ),
    )
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            spans=(
                PrivacyFilterSpan(
                    text_index=0,
                    start=8,
                    end=14,
                    label="secret",
                    blocker_type="credential",
                    entity_type="credential",
                ),
            ),
            entity_types=("credential",),
            blocker_types=("credential",),
            enabled=True,
            used=True,
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "Review token fragment"}],
            ),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_mask_and_send_fails_closed_when_privacy_filter_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "evaluate_ai_security_policy",
        lambda *_args, **_kwargs: AiSecurityPolicyDecision(
            effect="mask_and_send",
            reason_code=POLICY_MASK_AND_SEND_REASON,
        ),
    )
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="disabled",
            enabled=False,
            used=False,
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "public prompt"}],
            ),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_global_mask_action_masks_pii_when_no_policy_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "ai_security_data_protection_blocker_actions",
        lambda _db: {
            "sensitive_identifier": "block",
            "internal_url": "block",
            "pii": "mask_and_send",
            "security_document": "block",
        },
    )
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )

    execution = resolve_gateway_execution(
        _request(
            "files_grounded_chat",
            messages=[{"role": "user", "content": "Contact owner@example.com"}],
        ),
        _FakePolicyDb("external"),
    )

    assert execution.decision.chosen_pool == "external"
    assert execution.decision.mask_applied is True
    assert execution.decision.ai_security_policy_effect == "inherit"
    assert "owner@example.com" not in str(execution.messages)


def test_gateway_policy_block_external_does_not_reroute_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "ai_security_data_protection_blocker_actions",
        lambda _db: {
            "sensitive_identifier": "block",
            "internal_url": "block",
            "pii": "mask_and_send",
            "security_document": "block",
        },
    )
    monkeypatch.setattr(
        gateway_module,
        "evaluate_ai_security_policy",
        lambda *_args, **_kwargs: AiSecurityPolicyDecision(
            effect="block_external",
            reason_code="ai_security_policy_block_external",
            rule_id="rule-1",
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "Contact owner@example.com"}],
            ),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_inherit_cannot_override_global_block_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gateway_module,
        "ai_security_data_protection_blocker_actions",
        lambda _db: {
            "sensitive_identifier": "block",
            "internal_url": "block",
            "pii": "block",
            "security_document": "block",
        },
    )
    monkeypatch.setattr(
        gateway_module,
        "evaluate_ai_security_policy",
        lambda *_args, **_kwargs: AiSecurityPolicyDecision(
            effect="inherit",
            reason_code="no_matching_rule",
            rule_id="rule-1",
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        resolve_gateway_execution(
            _request(
                "files_grounded_chat",
                messages=[{"role": "user", "content": "Contact owner@example.com"}],
            ),
            _FakePolicyDb("external"),
        )
    assert exc_info.value.reason_code == "external_transfer_blocked"


def test_gateway_request_uses_domain_context_pack_messages() -> None:
    context_pack = AiGatewayContextPack(
        messages=[{"role": "user", "content": "server-built domain context"}],
        context_strategy="domain_context_pack",
        estimated_input_tokens=123,
    )

    execution = resolve_gateway_execution(
        _request(
            "chatbot",
            messages=[{"role": "user", "content": "stale client history"}],
            context_pack=context_pack,
        ),
        _FakePolicyDb(None),
    )

    assert execution.messages == context_pack.messages
    assert execution.decision.context_strategy == "domain_context_pack"
    assert execution.decision.estimated_input_tokens == 123


def test_gateway_passes_context_metadata_to_llm_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_complete_chat(*_args: Any, **kwargs: Any) -> tuple[object, object, object]:
        captured.update(kwargs)
        execution = kwargs["resolved_execution"]
        return object(), execution.decision, execution.config

    monkeypatch.setattr(gateway_module, "_complete_chat", fake_complete_chat)
    context_pack = AiGatewayContextPack(
        messages=[{"role": "user", "content": "domain context"}],
        context_strategy="domain_context_pack",
        estimated_input_tokens=321,
        source_kinds=("docs",),
        sensitivity_labels=("internal",),
        content_origin="internal_context",
    )

    complete_gateway_chat(
        _request("chatbot", context_pack=context_pack),
        _FakePolicyDb(None),
    )

    assert captured["audit_context_strategy"] == "domain_context_pack"
    assert captured["audit_estimated_input_tokens"] == 321
    assert captured["audit_content_origin"] == "internal_context"
    assert captured["audit_source_kinds"] == ("docs",)
    assert captured["audit_sensitivity_labels"] == ("internal",)


def test_execute_llm_uses_registered_admin_route_without_caller_model_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    workload = get_ai_capability_registry().resolve_llm_workload("chatbot")
    monkeypatch.setattr(
        gateway_module,
        "resolve_llm_workload_route",
        lambda *_args, **_kwargs: SimpleNamespace(
            workload=workload,
            route="external",
            provider_id="anthropic",
            adapter_provider="anthropic",
            endpoint_url="https://api.anthropic.com",
            api_key=SimpleNamespace(get_secret_value=lambda: "database-key"),
            model_key="claude-sonnet-4-6",
            local_max_output_tokens=32_768,
            external_max_output_tokens=65_536,
            max_output_tokens=65_536,
        ),
    )

    def fake_complete(request, db):
        captured["request"] = request
        captured["db"] = db
        return SimpleNamespace(text="ok"), SimpleNamespace(), request.workload_config

    monkeypatch.setattr(gateway_module, "complete_gateway_chat_text", fake_complete)
    db = object()
    result = execute_llm(
        "chatbot",
        LlmWorkloadContext(
            source="tests.registered_workload",
            actor_user_id="user-1",
            app_id="chatbot",
        ),
        db,  # type: ignore[arg-type]
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=100_000,
    )

    request = captured["request"]
    assert captured["db"] is db
    assert request.workload_id == "chatbot"
    assert request.pool_hint is None
    assert request.requested_provider == "anthropic"
    assert request.requested_model == "claude-sonnet-4-6"
    assert request.max_tokens == 65_536
    assert request.workload_config.api_key == "database-key"
    assert request.workload_config.base_url == "https://api.anthropic.com"
    assert request.workload_config.provider == "anthropic"
    assert result.config.default_model == "claude-sonnet-4-6"


def test_execute_llm_uses_route_cap_when_caller_omits_max_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    workload = get_ai_capability_registry().resolve_llm_workload("chatbot")
    monkeypatch.setattr(
        gateway_module,
        "resolve_llm_workload_route",
        lambda *_args, **_kwargs: SimpleNamespace(
            workload=workload,
            route="local",
            provider_id="local",
            adapter_provider="vllm",
            endpoint_url="http://local.test/v1",
            api_key=SimpleNamespace(get_secret_value=lambda: "local-key"),
            model_key="local-model",
            local_max_output_tokens=24_576,
            external_max_output_tokens=49_152,
            max_output_tokens=24_576,
        ),
    )

    def fake_complete(request, _db):
        captured["request"] = request
        return SimpleNamespace(text="ok"), SimpleNamespace(), request.workload_config

    monkeypatch.setattr(gateway_module, "complete_gateway_chat_text", fake_complete)
    execute_llm(
        "chatbot",
        LlmWorkloadContext(
            source="tests.registered_workload.default_cap",
            app_id="chatbot",
        ),
        object(),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": "hello"}],
    )

    assert captured["request"].max_tokens == 24_576


def test_llm_call_audit_payload_records_gateway_context_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_record_audit_event(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(audit_module, "_record_audit_event", fake_record_audit_event)

    audit_module.log_llm_call(
        source="tests.ai_gateway",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id=None,
        task_kind="chatbot",
        app_id="chatbot",
        policy="local_only",
        chosen_pool="local",
        decision_reason="task_local_only",
        forced_local=True,
        pii_hits=[],
        model="test-model",
        status="ok",
        latency_ms=1,
        max_tokens=8192,
        context_strategy="domain_context_pack",
        estimated_input_tokens=321,
        sensitivity_labels=["internal"],
        blocked_entity_types=["security_document"],
        content_origin="internal_context",
        source_kinds=["docs"],
    )

    payload = captured["payload"]
    assert payload["app_id"] == "chatbot"
    assert payload["context_strategy"] == "domain_context_pack"
    assert payload["estimated_input_tokens"] == 321
    assert payload["sensitivity_labels"] == ["internal"]
    assert payload["blocked_entity_types"] == ["security_document"]
    assert payload["content_origin"] == "internal_context"
    assert payload["source_kinds"] == ["docs"]
    assert "domain context" not in str(payload)
