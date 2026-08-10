from types import SimpleNamespace

import pytest

from ai_do_api.core import llm, llm_execution_adapters, llm_official_providers
from ai_do_api.core.settings import get_settings


LLM_ENV_KEYS = (
    "AI_DO_LLM_LOCAL_PROVIDER",
    "AI_DO_LLM_LOCAL_BASE_URL",
    "AI_DO_LLM_LOCAL_API_KEY",
    "AI_DO_LLM_LOCAL_DEFAULT_MODEL",
    "AI_DO_LLM_LOCAL_CANONICAL_MODEL",
    "AI_DO_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS",
    "AI_DO_LLM_EXTERNAL_ALLOWED_PROVIDERS",
    "AI_DO_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS",
    "AI_DO_LLM_OPENAI_BASE_URL",
    "AI_DO_LLM_OPENAI_DEFAULT_MODEL",
    "AI_DO_LLM_OPENAI_CANONICAL_MODEL",
    "AI_DO_LLM_ANTHROPIC_BASE_URL",
    "AI_DO_LLM_ANTHROPIC_DEFAULT_MODEL",
    "AI_DO_LLM_ANTHROPIC_CANONICAL_MODEL",
    "AI_DO_LLM_GEMINI_BASE_URL",
    "AI_DO_LLM_GEMINI_DEFAULT_MODEL",
    "AI_DO_LLM_GEMINI_CANONICAL_MODEL",
    "AI_DO_LLM_REQUEST_TIMEOUT_SECONDS",
    "AI_DO_LLM_HEALTHCHECK_ON_STARTUP",
    "AI_DO_LLM_REQUIRED",
)


class FakeModels:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[SimpleNamespace(id=model_id) for model_id in self._ids])


class FakeChatCompletions:
    def __init__(self, content: str) -> None:
        self._content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            model=str(kwargs["model"]),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )


class FakeClient:
    def __init__(self, ids: list[str], content: str = "ok") -> None:
        self.models = FakeModels(ids)
        self.chat = SimpleNamespace(completions=FakeChatCompletions(content))


def _clear_pool_client_cache() -> None:
    cache_clear = getattr(llm.get_pool_client, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    async_cache_clear = getattr(llm.get_async_pool_client, "cache_clear", None)
    if async_cache_clear is not None:
        async_cache_clear()


def _admin_resolved_local_config() -> llm.LlmPoolConfig:
    return llm.LlmPoolConfig(
        pool="local",
        provider="vllm",
        base_url="http://local-llm:8000/v1",
        api_key="",
        default_model="local/current-moe-test-model",
        canonical_model="local/current-moe-test-model",
        healthcheck_timeout_seconds=5,
        long_generation_timeout_seconds=30,
        requires_credentials=False,
    )


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in LLM_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv(
        "AI_DO_POSTGRES_DSN",
        "postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test",
    )
    get_settings.cache_clear()
    _clear_pool_client_cache()
    yield
    get_settings.cache_clear()
    _clear_pool_client_cache()


def test_resolved_pool_health_ready_when_admin_model_exists() -> None:
    health = llm.check_resolved_pool_health(
        _admin_resolved_local_config(),
        live=True,
        sync_client_factory=lambda pool, external_provider=None: FakeClient(
            ["local/current-moe-test-model"]
        ),
    )

    assert health.ready is True
    assert health.status == "ready"


def test_pool_config_requires_credentials_by_default() -> None:
    config = llm.LlmPoolConfig(
        pool="external",
        provider="plugin",
        base_url="https://plugin.example/v1",
        api_key="",
        default_model="plugin-default",
        canonical_model="plugin-default",
        healthcheck_timeout_seconds=5,
        long_generation_timeout_seconds=30,
    )

    assert config.configured is False


def test_pool_config_accepts_header_credentials_without_api_key() -> None:
    config = llm.LlmPoolConfig(
        pool="external",
        provider="plugin",
        base_url="https://plugin.example/v1",
        api_key="",
        default_model="plugin-default",
        canonical_model="plugin-default",
        healthcheck_timeout_seconds=5,
        long_generation_timeout_seconds=30,
        default_headers={"Authorization": "Bearer plugin-token"},
    )

    assert config.configured is True


def test_local_pool_environment_cannot_select_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DO_LLM_LOCAL_API_KEY", "")
    monkeypatch.setenv("AI_DO_LLM_LOCAL_DEFAULT_MODEL", "local/current-moe-test-model")
    monkeypatch.setenv("AI_DO_LLM_LOCAL_CANONICAL_MODEL", "local/current-moe-test-model")
    get_settings.cache_clear()

    config = llm.get_pool_config("local")

    assert config.requires_credentials is False
    assert config.default_model == ""
    assert config.canonical_model == ""
    assert config.configured is False


def test_external_allowed_provider_allowlist_does_not_fallback_to_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DO_LLM_EXTERNAL_ALLOWED_PROVIDERS", "typo-provider")
    get_settings.cache_clear()

    assert llm.get_allowed_external_llm_providers() == ()
    with pytest.raises(ValueError, match="external LLM provider is not allowed"):
        llm.normalize_external_provider("openai")


def test_legacy_external_api_key_envs_are_not_runtime_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for provider in ("OPENAI", "ANTHROPIC", "GEMINI"):
        monkeypatch.setenv(f"AI_DO_LLM_{provider}_API_KEY", "legacy-secret")
    get_settings.cache_clear()

    settings = get_settings()

    assert not hasattr(settings, "llm_openai_api_key")
    assert not hasattr(settings, "llm_anthropic_api_key")
    assert not hasattr(settings, "llm_gemini_api_key")
    assert all(
        llm.get_pool_config("external", external_provider=provider).api_key == ""
        for provider in ("openai", "anthropic", "gemini")
    )


def test_resolved_pool_health_reports_missing_admin_model() -> None:
    health = llm.check_resolved_pool_health(
        _admin_resolved_local_config(),
        live=True,
        sync_client_factory=lambda pool, external_provider=None: FakeClient(
            ["other-local-model"]
        ),
    )

    assert health.ready is False
    assert health.status == "model_missing"
    assert "other-local-model" in (health.public_dict()["detail"] or "")


def test_legacy_external_pool_health_fails_closed_without_db_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DO_LLM_EXTERNAL_ALLOWED_PROVIDERS", "anthropic")
    monkeypatch.setenv("AI_DO_LLM_REQUEST_TIMEOUT_SECONDS", "7.5")
    get_settings.cache_clear()

    calls: list[tuple[str, str, float]] = []

    def fake_check(config, timeout_seconds):  # type: ignore[no-untyped-def]
        calls.append((config.provider, config.default_model, timeout_seconds))
        return SimpleNamespace(status="unavailable", detail="probe failed")

    monkeypatch.setattr(
        llm_execution_adapters,
        "check_official_provider_health",
        fake_check,
    )

    health = llm.check_pool_health("external", external_provider="anthropic")

    assert health.status == "not_configured"
    assert calls == []


def test_official_provider_health_maps_model_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NotFoundError(Exception):
        status_code = 404

    def fake_check(config, timeout_seconds):  # type: ignore[no-untyped-def]
        del config, timeout_seconds
        raise NotFoundError("model not found")

    monkeypatch.setattr(
        llm_official_providers,
        "_check_anthropic_health",
        fake_check,
    )

    health = llm_official_providers.check_official_provider_health(
        SimpleNamespace(
            provider="anthropic",
            base_url="https://api.anthropic.com",
            api_key="test-key",
            default_model="claude-test",
        ),
        timeout_seconds=1,
    )

    assert health.status == "model_missing"


def test_legacy_pool_health_does_not_accept_environment_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AI_DO_LLM_LOCAL_DEFAULT_MODEL", "local/current-moe-test-model"
    )
    monkeypatch.setenv("AI_DO_LLM_EXTERNAL_ALLOWED_PROVIDERS", "openai")

    monkeypatch.setattr(
        llm,
        "get_pool_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unconfigured pools must not call providers")
        ),
    )

    dual = llm.check_all_pools_health()

    assert dual.local.status == "not_configured"
    assert dual.external is not None
    assert dual.external.ready is False
    assert dual.external.status == "not_configured"
    assert dual.external.canonical_model == ""


def test_configured_health_does_not_probe_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AI_DO_LLM_LOCAL_DEFAULT_MODEL", "local/current-moe-test-model"
    )
    monkeypatch.setenv(
        "AI_DO_LLM_LOCAL_CANONICAL_MODEL", "local/current-moe-test-model"
    )
    monkeypatch.setattr(
        llm,
        "get_pool_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("configured health must not call providers")
        ),
    )

    dual = llm.check_configured_pools_health()

    assert dual.ready is False
    assert dual.local.status == "not_configured"
    assert "base_url" not in dual.public_dict(include_base_url=False)["local"]


def test_choose_pool_defaults_to_local_only_without_policy_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_do_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="unknown_task_kind_xyz",
        app_id="chatbot",
    )
    pool, decision = choose_pool(context, ["hello world"], _FakeDb())

    assert pool == "local"
    assert decision.policy == "local_only"
    assert decision.chosen_pool == "local"
    assert decision.reason == "policy_local_only"
    assert decision.forced_local is False
    assert decision.pii_hits == []


def test_llm_task_context_requires_app_id() -> None:
    from ai_do_api.core.llm import LlmTaskContext

    with pytest.raises(ValueError, match="LLM app_id is required"):
        LlmTaskContext(
            source="api.chat",
            actor_user_id="user-1",
            workspace_id="ws-1",
            task_kind="chatbot",
            app_id="",
        )


def test_choose_pool_local_hint_forces_local_even_on_external_policy() -> None:
    from ai_do_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
        app_id="chatbot",
    )
    pool, decision = choose_pool(
        context,
        ["benign sentence"],
        _FakeDb(),
        pool_hint="local",
        policy_override="external",
    )

    assert pool == "local"
    assert decision.policy == "external"
    assert decision.chosen_pool == "local"
    assert decision.forced_local is True
    assert decision.reason == "local_hint"


def test_choose_pool_does_not_apply_payload_security_in_core_transport() -> None:
    from ai_do_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
        app_id="chatbot",
    )
    prompt = "주민번호는 900101-1234567 입니다."
    pool, decision = choose_pool(
        context,
        [prompt],
        _FakeDb(),
        policy_override="external",
    )

    assert pool == "external"
    assert decision.policy == "external"
    assert decision.chosen_pool == "external"
    assert decision.forced_local is False
    assert decision.reason == "explicit_external_route"
    assert decision.pii_hits == []


def test_choose_pool_does_not_rescan_security_documents_in_core_transport() -> None:
    from ai_do_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
        app_id="chatbot",
    )
    pool, decision = choose_pool(
        context,
        ["보안 문서 VPN 접근 제어 정책 요약"],
        _FakeDb(),
        policy_override="external",
    )

    assert pool == "external"
    assert decision.policy == "external"
    assert decision.chosen_pool == "external"
    assert decision.forced_local is False
    assert decision.reason == "explicit_external_route"
    assert decision.blocked_entity_types == []


def test_choose_pool_uses_external_when_policy_external_and_no_pii() -> None:
    from ai_do_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
        app_id="chatbot",
    )
    pool, decision = choose_pool(
        context,
        ["totally benign sentence"],
        _FakeDb(),
        policy_override="external",
    )

    assert pool == "external"
    assert decision.policy == "external"
    assert decision.chosen_pool == "external"
    assert decision.reason == "explicit_external_route"
    assert decision.forced_local is False
    assert decision.pii_hits == []


def test_scan_pii_matches_space_separated_kr_rrn_and_phone() -> None:
    from ai_do_api.core.pii import scan_pii

    hits = scan_pii(
        [
            "주민번호는 900101 1234567 입니다.",
            "연락처는 010 1234 5678 입니다.",
        ]
    )

    assert [hit.pattern for hit in hits] == ["rrn_kr", "phone_kr"]


def test_scan_pii_matches_overlong_kr_rrn_suffix() -> None:
    from ai_do_api.core.pii import scan_pii

    hits = scan_pii(["주민번호형 식별자는 851212-10456712 입니다."])

    assert [hit.pattern for hit in hits] == ["rrn_kr"]


def test_scan_pii_matches_separatorless_kr_phone() -> None:
    from ai_do_api.core.pii import scan_pii

    hits = scan_pii(["연락처는 01012345678 입니다."])

    assert [hit.pattern for hit in hits] == ["phone_kr"]


def test_completion_result_normalizes_object_response() -> None:
    response = SimpleNamespace(
        model="local/current-moe-test-model",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="요약 결과"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=3,
            completion_tokens=5,
            total_tokens=8,
        ),
    )

    result = llm.completion_result(response)

    assert result.text == "요약 결과"
    assert result.model == "local/current-moe-test-model"
    assert result.finish_reason == "stop"
    assert result.usage == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "total_tokens": 8,
    }


def test_completion_result_normalizes_dict_response_with_content_parts() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"text": "첫 번째 문장"},
                        {"text": "두 번째 문장"},
                    ]
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 2,
            "completion_tokens": 4,
            "total_tokens": 6,
        },
    }

    result = llm.completion_result(response)

    assert result.text == "첫 번째 문장\n두 번째 문장"
    assert result.model is None
    assert result.finish_reason == "stop"
    assert result.usage == {
        "prompt_tokens": 2,
        "completion_tokens": 4,
        "total_tokens": 6,
    }


def test_official_anthropic_stream_emits_deltas_usage_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: dict[str, object] = {}

    class _FakeAnthropicStream:
        text_stream = iter(["hel", "lo"])

        def get_final_message(self) -> SimpleNamespace:
            return SimpleNamespace(
                stop_reason="end_turn",
                usage=SimpleNamespace(input_tokens=2, output_tokens=3),
            )

    class _FakeAnthropicStreamManager:
        def __enter__(self) -> _FakeAnthropicStream:
            return _FakeAnthropicStream()

        def __exit__(self, *_args: object) -> None:
            return None

    class _FakeAnthropicMessages:
        def stream(self, **request: object) -> _FakeAnthropicStreamManager:
            captured_request.update(request)
            return _FakeAnthropicStreamManager()

    class _FakeAnthropicClient:
        messages = _FakeAnthropicMessages()

    monkeypatch.setattr(
        llm_official_providers,
        "_anthropic_client",
        lambda config, timeout_seconds: _FakeAnthropicClient(),
    )

    chunks = list(
        llm_official_providers.stream_official_provider_chat(
            SimpleNamespace(
                provider="anthropic",
                base_url="",
                api_key="test-key",
                default_model="claude-test",
            ),
            {
                "model": "claude-test",
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "hello"},
                ],
                "max_tokens": 11,
                "temperature": 0.2,
            },
            timeout_seconds=7,
        )
    )

    assert captured_request == {
        "model": "claude-test",
        "max_tokens": 11,
        "messages": [{"role": "user", "content": "hello"}],
        "system": "system",
        "temperature": 0.2,
    }
    assert [(chunk.kind, chunk.text, chunk.usage, chunk.finish_reason) for chunk in chunks] == [
        ("content", "hel", None, None),
        ("content", "lo", None, None),
        (
            "usage",
            None,
            {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            None,
        ),
        ("done", None, None, "stop"),
    ]


def test_official_gemini_stream_emits_deltas_usage_and_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: dict[str, object] = {}

    class _FakeGeminiModels:
        def generate_content_stream(self, **request: object):
            captured_request.update(request)
            yield SimpleNamespace(text="hel", usage_metadata=None, candidates=[])
            yield SimpleNamespace(
                text="lo",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=2,
                    candidates_token_count=3,
                    total_token_count=5,
                ),
                candidates=[SimpleNamespace(finish_reason="STOP")],
            )

    class _FakeGeminiClient:
        models = _FakeGeminiModels()

        def __enter__(self) -> "_FakeGeminiClient":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(
        llm_official_providers,
        "_gemini_client",
        lambda config, timeout_seconds: _FakeGeminiClient(),
    )

    chunks = list(
        llm_official_providers.stream_official_provider_chat(
            SimpleNamespace(
                provider="gemini",
                base_url="",
                api_key="test-key",
                default_model="gemini-test",
            ),
            {
                "model": "gemini-test",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 11,
                "temperature": 0.2,
            },
            timeout_seconds=7,
        )
    )

    assert captured_request["model"] == "gemini-test"
    assert captured_request["contents"] == "user: hello"
    assert getattr(captured_request["config"], "max_output_tokens") == 11
    assert [(chunk.kind, chunk.text, chunk.usage, chunk.finish_reason) for chunk in chunks] == [
        ("content", "hel", None, None),
        ("content", "lo", None, None),
        (
            "usage",
            None,
            {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            None,
        ),
        ("done", None, None, "stop"),
    ]


def test_official_provider_finish_reasons_normalize_to_stream_contract() -> None:
    assert (
        llm_official_providers._normalize_finish_reason("anthropic", "end_turn")
        == "stop"
    )
    assert (
        llm_official_providers._normalize_finish_reason("anthropic", "max_tokens")
        == "length"
    )
    assert (
        llm_official_providers._normalize_finish_reason("anthropic", "tool_use")
        == "tool_calls"
    )
    assert llm_official_providers._normalize_finish_reason("gemini", "STOP") == "stop"
    assert (
        llm_official_providers._normalize_finish_reason("gemini", "MAX_TOKENS")
        == "length"
    )
