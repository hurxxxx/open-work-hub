from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.ai.external_gateway import AiExternalCapabilityRequest
from open_work_hub_api.domains.ai import external_gateway
from open_work_hub_api.domains.ai.model_settings_service import AiModelSettingsError
from open_work_hub_api.domains.web_search import router, service


def _settings(**overrides) -> Settings:
    values = {}
    values.update(overrides)
    return Settings(**values)


def _route(**overrides):
    values = {
        "route": "external",
        "provider_id": "anthropic",
        "adapter_provider": "anthropic",
        "model_key": "claude-db-test",
        "endpoint_url": "https://anthropic.db.example",
        "api_key": SecretStr("db-anthropic-key"),
        "max_output_tokens": 65_536,
        "workload": SimpleNamespace(task_kind="web_search_answer"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _decode_sse_payload(event: dict[str, str]) -> dict:
    return json.loads(event["data"])


def test_prepare_web_search_execution_uses_external_registered_route(monkeypatch) -> None:
    captured: dict[str, object] = {}
    route = _route(model_key="selected-model")

    class FakeExecution:
        decision = SimpleNamespace(mask_applied=False)

        def sanitized_text(self, _index: int = 0, *, fallback: str = "") -> str:
            return fallback

    def fake_begin(request, **kwargs):
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeExecution()

    monkeypatch.setattr(service, "resolve_llm_workload_route", lambda *_args, **_kwargs: route)
    monkeypatch.setattr(service, "begin_external_capability", fake_begin)

    prepared = service.prepare_web_search_execution(
        question="등록 경로 검색",
        profile_id="general",
        app_id="web-search",
        actor_user_id="user-1",
        db=object(),
        settings=_settings(),
    )

    assert prepared.route is route
    assert prepared.workload_id == "web_search.answer"
    assert captured["request"].provider == "anthropic"
    assert captured["request"].task_kind == "web_search_answer"


def test_prepare_web_search_execution_rejects_local_route(monkeypatch) -> None:
    route = _route(route="local", provider_id="local", model_key="local-model")
    monkeypatch.setattr(service, "resolve_llm_workload_route", lambda *_args: route)

    with pytest.raises(service.WebSearchConfigurationError, match="external LLM route"):
        service.prepare_web_search_execution(
            question="로컬 경로 거부",
            app_id="web-search",
            actor_user_id="user-1",
            db=object(),
            settings=_settings(),
        )


def test_prepare_web_search_execution_maps_database_route_error(monkeypatch) -> None:
    def missing_route(*_args):
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_key_required",
        )

    monkeypatch.setattr(service, "resolve_llm_workload_route", missing_route)

    with pytest.raises(service.WebSearchConfigurationError, match="not configured"):
        service.prepare_web_search_execution(
            question="DB 경로 오류",
            app_id="web-search",
            actor_user_id="user-1",
            db=object(),
            settings=_settings(),
        )


@pytest.mark.anyio
async def test_stream_web_search_uses_registered_hermes_result_and_budget(monkeypatch):
    from open_work_hub_api.core.llm_adapters import StreamChunk

    audit_records = []
    monkeypatch.setattr(
        external_gateway, "log_ai_external_call", lambda **kwargs: audit_records.append(kwargs)
    )
    monkeypatch.setattr(service, "resolve_llm_workload_route", lambda *_args: _route())
    captured = []

    async def native_stream(workload_id, context, db, **kwargs):
        captured.append((workload_id, context, kwargs))
        yield (
            StreamChunk(kind="usage", usage={"prompt_tokens": 10, "completion_tokens": 20}),
            None,
            SimpleNamespace(default_model="admin-selected-model"),
        )
        yield (
            StreamChunk(
                kind="done",
                structured_output={
                    "answer": "Current information.[1]",
                    "citations": [
                        {"url": "https://example.com/news", "title": "Example", "cited_text": None}
                    ],
                },
            ),
            None,
            SimpleNamespace(default_model="admin-selected-model"),
        )

    monkeypatch.setattr(service, "stream_llm", native_stream)
    prepared = service.prepare_web_search_execution(
        question="Public news",
        max_uses=3,
        app_id="web-search",
        actor_user_id="user-1",
        db=None,
        settings=_settings(),
    )
    events = [
        event
        async for event in service.stream_web_search_answer(
            question="Public news", max_uses=3, prepared_execution=prepared, db=object()
        )
    ]
    assert len(events) == 2
    assert events[0].text == "Current information.[1]"
    assert events[1].response.citations[0].url == "https://example.com/news"
    assert events[1].response.usage.output_tokens == 20
    assert events[1].response.model == "admin-selected-model"
    assert captured[0][0] == "web_search.answer"
    assert captured[0][1].native_tool_limit == 3
    assert "citations" in captured[0][2]["output_schema"]["properties"]
    assert audit_records[0]["status"] == "ok"


@pytest.mark.anyio
async def test_web_search_blocks_pii_before_hermes_dispatch(
    monkeypatch,
) -> None:
    audit_records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: audit_records.append(kwargs),
    )

    monkeypatch.setattr(service, "resolve_llm_workload_route", lambda *_args: _route())
    monkeypatch.setattr(
        service,
        "stream_llm",
        lambda *_args, **_kwargs: pytest.fail(
            "Hermes must not dispatch after gateway policy denial"
        ),
    )

    with pytest.raises(service.WebSearchPolicyError) as error:
        service.prepare_web_search_execution(
            question="owner@example.com 최신 소식 알려줘",
            app_id="web-search",
            actor_user_id="user-1",
            db=None,
            settings=_settings(),
        )

    assert str(error.value) == "pii_detected"
    assert audit_records[0]["status"] == "blocked"
    assert audit_records[0]["policy_reason"] == "pii_detected"
    assert audit_records[0]["pii_hits"] == ["email"]


def test_web_search_policy_denied_message_hides_internal_reason_code() -> None:
    message = router._web_search_policy_denied_message("pii_detected")

    assert "웹 검색으로 처리하기 어렵습니다" in message
    assert "공개 가능한 내용" in message
    assert "개인정보" not in message
    assert "차단" not in message
    assert "보안 정책" not in message
    assert "pii_detected" not in message


@pytest.mark.anyio
async def test_web_search_policy_denial_does_not_persist_sensitive_prompt(
    monkeypatch,
) -> None:
    def deny_before_persistence(**_kwargs):
        raise service.WebSearchPolicyError("pii_detected")

    monkeypatch.setattr(service, "prepare_web_search_execution", deny_before_persistence)
    monkeypatch.setattr(
        router.app_persistence,
        "append_user_and_attach",
        lambda **_kwargs: pytest.fail("blocked web search prompt must not be persisted"),
    )

    events = [
        _decode_sse_payload(event)
        async for event in router._ask_stream_publisher(
            payload=SimpleNamespace(
                question="owner@example.com 최신 소식 알려줘",
                max_uses=1,
                conversation_id=None,
            ),
            app_id="web-search",
            profile_id="general",
            conversation_scope_ref="web_search",
            db=object(),
            current_user=SimpleNamespace(id="user-1"),
        )
    ]

    assert [event["type"] for event in events] == ["error"]
    assert events[0]["data"]["code"] == "web_search.policy_denied"
    assert "웹 검색으로 처리하기 어렵습니다" in events[0]["data"]["message"]
    assert "개인정보" not in events[0]["data"]["message"]


@pytest.mark.anyio
async def test_web_search_masked_prompt_persists_sanitized_text(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeExecution:
        decision = SimpleNamespace(mask_applied=True)
        request = AiExternalCapabilityRequest(
            source="api.general.web_search",
            actor_user_id="user-1",
            principal_id="user-1",
            task_kind="web_search",
            capability="web_search",
            provider="anthropic",
            app="web-search",
            input_texts=["owner@example.com 최신 소식 알려줘"],
        )

        def sanitized_text(self, _index: int = 0, *, fallback: str = "") -> str:
            return "[masked:pii] 최신 소식 알려줘"

    def prepare(**_kwargs):
        return service.PreparedWebSearchExecution(
            settings=_settings(),
            workload_id="web_search.answer",
            route=SimpleNamespace(route="external", model_key="claude-test"),
            external_execution=FakeExecution(),
            provider_question="[masked:pii] 최신 소식 알려줘",
        )

    def append_user_and_attach(*_args, **kwargs):
        captured["content"] = kwargs["content"]
        return SimpleNamespace(conversation=SimpleNamespace(id="conversation-1"))

    async def no_provider_events(**kwargs):
        captured["conversation_id"] = kwargs[
            "prepared_execution"
        ].external_execution.request.conversation_id
        if False:
            yield None

    monkeypatch.setattr(service, "prepare_web_search_execution", prepare)
    monkeypatch.setattr(service, "stream_web_search_answer", no_provider_events)
    monkeypatch.setattr(router.app_persistence, "append_user_and_attach", append_user_and_attach)

    events = [
        _decode_sse_payload(event)
        async for event in router._ask_stream_publisher(
            payload=SimpleNamespace(
                question="owner@example.com 최신 소식 알려줘",
                max_uses=1,
                conversation_id=None,
            ),
            app_id="web-search",
            profile_id="general",
            conversation_scope_ref="web_search",
            db=object(),
            current_user=SimpleNamespace(id="user-1"),
        )
    ]

    assert captured["content"] == "[masked:pii] 최신 소식 알려줘"
    assert captured["conversation_id"] == "conversation-1"
    assert [event["type"] for event in events] == ["conversation_attached"]
    assert events[0]["data"]["display_question"] == "[masked:pii] 최신 소식 알려줘"


@pytest.mark.anyio
async def test_prepare_web_search_execution_requires_database_route_credential(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        service,
        "resolve_llm_workload_route",
        lambda *_args: _route(api_key=None),
    )

    with pytest.raises(service.WebSearchConfigurationError, match="API key"):
        service.prepare_web_search_execution(
            question="검색",
            app_id="web-search",
            actor_user_id="user-1",
            db=None,
            settings=_settings(),
        )
