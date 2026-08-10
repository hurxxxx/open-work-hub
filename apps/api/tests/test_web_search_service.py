from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from open_alm_api.core.settings import Settings
from open_alm_api.domains.ai.external_gateway import AiExternalCapabilityRequest
from open_alm_api.domains.ai import external_gateway
from open_alm_api.domains.ai.model_settings_service import AiModelSettingsError
from open_alm_api.domains.web_search import router, service


class _AsyncTextStream:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        self._iterator = iter(self._chunks)
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeStream:
    def __init__(self, chunks: list[str], final_message: object) -> None:
        self.text_stream = _AsyncTextStream(chunks)
        self._final_message = final_message

    async def get_final_message(self) -> object:
        return self._final_message


class _FakeStreamManager:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream

    async def __aenter__(self) -> _FakeStream:
        return self._stream

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        return None


class _FakeMessages:
    def __init__(self, stream: _FakeStream) -> None:
        self._stream = stream
        self.captured_request: dict | None = None

    def stream(self, **kwargs):
        self.captured_request = kwargs
        return _FakeStreamManager(self._stream)


class _FakeClient:
    def __init__(self, stream: _FakeStream) -> None:
        self.messages = _FakeMessages(stream)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


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
        workspace_id="workspace-1",
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
            workspace_id="workspace-1",
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
            workspace_id="workspace-1",
            app_id="web-search",
            actor_user_id="user-1",
            db=object(),
            settings=_settings(),
        )


@pytest.mark.anyio
async def test_stream_web_search_answer_streams_text_and_final_citations(
    monkeypatch,
) -> None:
    audit_records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: audit_records.append(kwargs),
    )
    final_message = SimpleNamespace(
        model="claude-test",
        content=[
            SimpleNamespace(
                text="현재 정보입니다.",
                citations=[
                    SimpleNamespace(
                        url="https://example.com/news",
                        title="Example News",
                        cited_text="quoted evidence",
                    )
                ],
            )
        ],
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=20,
            server_tool_use=SimpleNamespace(web_search_requests=1),
        ),
    )
    fake_client = _FakeClient(_FakeStream(["현재 ", "정보입니다."], final_message))
    route = _route()
    monkeypatch.setattr(service, "resolve_llm_workload_route", lambda *_args: route)
    prepared = service.prepare_web_search_execution(
        question="최신 뉴스 알려줘",
        max_uses=3,
        workspace_id="workspace-1",
        app_id="web-search",
        actor_user_id="user-1",
        db=None,
        settings=_settings(),
    )
    captured_route: list[object] = []

    events = [
        event
        async for event in service.stream_web_search_answer(
            question="최신 뉴스 알려줘",
            max_uses=3,
            prepared_execution=prepared,
            client_factory=lambda resolved_route: (
                captured_route.append(resolved_route) or fake_client
            ),
        )
    ]

    assert [type(event) for event in events] == [
        service.WebSearchAnswerDelta,
        service.WebSearchAnswerDelta,
        service.WebSearchAnswerComplete,
    ]
    assert events[0].text == "현재 "
    complete = events[-1]
    assert isinstance(complete, service.WebSearchAnswerComplete)
    assert complete.response.answer == "현재 정보입니다.[1]"
    assert complete.response.citations[0].url == "https://example.com/news"
    assert complete.response.usage is not None
    assert complete.response.usage.web_search_requests == 1
    assert fake_client.closed is True
    assert fake_client.messages.captured_request is not None
    assert fake_client.messages.captured_request["tools"] == [
        {
            "type": service.WEB_SEARCH_TOOL_TYPE,
            "name": "web_search",
            "max_uses": 3,
        }
    ]
    assert fake_client.messages.captured_request["system"] == service.SYSTEM_PROMPT
    assert fake_client.messages.captured_request["model"] == "claude-db-test"
    assert captured_route == [route]
    assert audit_records[0]["status"] == "ok"
    assert audit_records[0]["capability"] == "web_search"
    assert audit_records[0]["provider"] == "anthropic"


@pytest.mark.anyio
async def test_stream_web_search_answer_blocks_pii_before_client_factory(
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
        "_anthropic_client_for_route",
        lambda *_args, **_kwargs: pytest.fail(
            "provider client must not be created after gateway policy denial"
        ),
    )

    with pytest.raises(service.WebSearchPolicyError) as error:
        service.prepare_web_search_execution(
            question="owner@example.com 최신 소식 알려줘",
            workspace_id="workspace-1",
            app_id="web-search",
            actor_user_id="user-1",
            db=None,
            settings=_settings(),
        )

    assert str(error.value) == "pii_detected"
    assert audit_records[0]["status"] == "blocked"
    assert audit_records[0]["policy_reason"] == "pii_detected"
    assert audit_records[0]["pii_hits"] == ["email"]


def test_anthropic_web_search_request_uses_profile_prompts() -> None:
    research_request = service._anthropic_web_search_request(
        question="전고체 배터리 논문 동향",
        max_uses=8,
        profile_id="research-trends",
        model="claude-research-db",
        max_tokens=4096,
    )
    standards_request = service._anthropic_web_search_request(
        question="UNECE R155 변경사항",
        max_uses=8,
        profile_id="standards-monitor",
        model="claude-standards-db",
        max_tokens=2048,
    )

    assert "research and technology trend analyst" in research_request["system"]
    assert "standards and regulatory monitoring analyst" in standards_request["system"]
    assert research_request["model"] == "claude-research-db"
    assert standards_request["model"] == "claude-standards-db"
    assert research_request["max_tokens"] == 4096
    assert standards_request["max_tokens"] == 2048
    assert standards_request["tools"][0]["max_uses"] == 8


def test_anthropic_client_uses_resolved_database_route(monkeypatch) -> None:
    import anthropic

    captured: dict[str, object] = {}
    expected_client = object()

    def fake_client(**kwargs):
        captured.update(kwargs)
        return expected_client

    monkeypatch.setattr(anthropic, "AsyncAnthropic", fake_client)
    route = _route(
        endpoint_url="https://anthropic.db.example/custom/",
        api_key=SecretStr("decrypted-database-key"),
    )

    client = service._anthropic_client_for_route(route, settings=_settings())

    assert client is expected_client
    assert captured == {
        "api_key": "decrypted-database-key",
        "base_url": "https://anthropic.db.example/custom",
        "timeout": _settings().llm_external_long_generation_timeout_seconds,
    }


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
            current_workspace=SimpleNamespace(id="workspace-1"),
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
            workspace_id="workspace-1",
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
            current_workspace=SimpleNamespace(id="workspace-1"),
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
            workspace_id="workspace-1",
            app_id="web-search",
            actor_user_id="user-1",
            db=None,
            settings=_settings(),
        )
