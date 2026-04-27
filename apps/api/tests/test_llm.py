from types import SimpleNamespace

import pytest

from aidoo_api.core import llm
from aidoo_api.core.settings import get_settings


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


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DOOWON_POSTGRES_DSN",
        "postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
    )
    get_settings.cache_clear()
    _clear_pool_client_cache()
    yield
    get_settings.cache_clear()
    _clear_pool_client_cache()


def test_llm_settings_default_to_local_mlx() -> None:
    settings = get_settings()

    assert settings.llm_local_provider == "mlx-lm"
    assert settings.llm_local_base_url == "http://127.0.0.1:8080/v1"
    assert settings.llm_local_api_key == "mlx"
    assert settings.llm_local_default_model == "mlx-community/Qwen3.6-35B-A3B-4bit"
    assert settings.llm_local_canonical_model == "qwen/qwen3.6-35b-a3b"
    assert settings.llm_external_enabled is True
    assert settings.llm_external_default_model == "qwen/qwen3.6-35b-a3b"
    assert settings.llm_request_timeout_seconds == 60.0
    assert settings.llm_local_long_generation_timeout_seconds == 1200.0


def test_pool_health_ready_when_configured_model_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DOOWON_LLM_LOCAL_DEFAULT_MODEL", "mlx-community/Qwen3.6-35B-A3B-4bit"
    )
    monkeypatch.setattr(
        llm,
        "get_pool_client",
        lambda pool: FakeClient(["mlx-community/Qwen3.6-35B-A3B-4bit"]),
    )

    health = llm.check_pool_health("local")

    assert health.ready is True
    assert health.status == "ready"


def test_pool_health_reports_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DOOWON_LLM_LOCAL_DEFAULT_MODEL", "mlx-community/Qwen3.6-35B-A3B-4bit"
    )
    monkeypatch.setattr(llm, "get_pool_client", lambda pool: FakeClient(["gemma4:31b"]))

    health = llm.check_pool_health("local")

    assert health.ready is False
    assert health.status == "model_missing"
    assert "gemma4:31b" in (health.detail or "")


def test_dual_health_reports_each_pool_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DOOWON_LLM_LOCAL_DEFAULT_MODEL", "mlx-community/Qwen3.6-35B-A3B-4bit"
    )
    monkeypatch.setenv("DOOWON_LLM_EXTERNAL_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("DOOWON_LLM_EXTERNAL_DEFAULT_MODEL", "qwen/qwen3.6-35b-a3b")

    def fake_pool_client(pool: str) -> FakeClient:
        if pool == "external":
            return FakeClient(["qwen/qwen3.6-35b-a3b"])
        return FakeClient(["gemma4:31b"])

    monkeypatch.setattr(llm, "get_pool_client", fake_pool_client)

    dual = llm.check_all_pools_health()

    assert dual.local.status == "model_missing"
    assert dual.external is not None
    assert dual.external.ready is True
    assert dual.external.canonical_model == "qwen/qwen3.6-35b-a3b"


def test_choose_pool_defaults_to_local_only_without_policy_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aidoo_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self_inner):  # noqa: ANN001
                    return None

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="unknown_task_kind_xyz",
    )
    pool, decision = choose_pool(context, ["hello world"], _FakeDb())

    assert pool == "local"
    assert decision.policy == "local_only"
    assert decision.chosen_pool == "local"
    assert decision.reason == "policy_local_only"
    assert decision.forced_local is False
    assert decision.pii_hits == []


def test_choose_pool_local_hint_forces_local_even_on_external_policy() -> None:
    from aidoo_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self_inner):  # noqa: ANN001
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
    )
    pool, decision = choose_pool(
        context,
        ["benign sentence"],
        _FakeDb(),
        pool_hint="local",
    )

    assert pool == "local"
    assert decision.policy == "external"
    assert decision.chosen_pool == "local"
    assert decision.forced_local is True
    assert decision.reason == "local_hint"


def test_choose_pool_forces_local_when_pii_detected_in_external_policy() -> None:
    from aidoo_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self_inner):  # noqa: ANN001
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
    )
    prompt = "주민번호는 900101-1234567 입니다."
    pool, decision = choose_pool(context, [prompt], _FakeDb())

    assert pool == "local"
    assert decision.policy == "external"
    assert decision.chosen_pool == "local"
    assert decision.forced_local is True
    assert decision.reason == "pii_detected"
    assert "rrn_kr" in decision.pii_hits


def test_choose_pool_uses_external_when_policy_external_and_no_pii() -> None:
    from aidoo_api.core.llm import LlmTaskContext, choose_pool

    class _FakeDb:
        def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self_inner):  # noqa: ANN001
                    return "external"

            return _Result()

    context = LlmTaskContext(
        source="api.chat",
        actor_user_id="user-1",
        workspace_id="ws-1",
        task_kind="allowed_external",
    )
    pool, decision = choose_pool(context, ["totally benign sentence"], _FakeDb())

    assert pool == "external"
    assert decision.policy == "external"
    assert decision.chosen_pool == "external"
    assert decision.reason == "policy_external"
    assert decision.forced_local is False
    assert decision.pii_hits == []


def test_scan_pii_matches_space_separated_kr_rrn_and_phone() -> None:
    from aidoo_api.core.pii import scan_pii

    hits = scan_pii(
        [
            "주민번호는 900101 1234567 입니다.",
            "연락처는 010 1234 5678 입니다.",
        ]
    )

    assert [hit.pattern for hit in hits] == ["rrn_kr", "phone_kr"]


def test_scan_pii_matches_separatorless_kr_phone() -> None:
    from aidoo_api.core.pii import scan_pii

    hits = scan_pii(["연락처는 01012345678 입니다."])

    assert [hit.pattern for hit in hits] == ["phone_kr"]
