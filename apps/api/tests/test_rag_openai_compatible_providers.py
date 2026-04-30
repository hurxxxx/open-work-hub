from __future__ import annotations

import httpx
import pytest

import aidoo_api.domains.rag.providers.openai_compatible as provider_module
from aidoo_api.domains.rag.contracts import RagProjection, RagVectorSearchHit
from aidoo_api.domains.rag.providers.openai_compatible import (
    DeepInfraEmbeddingClient,
    DeepInfraRerankClient,
    OpenAICompatibleRerankClient,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)


class _StubResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text or ""
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


def _hit(chunk_id: str, text: str, score: float = 0.1) -> RagVectorSearchHit:
    return RagVectorSearchHit(
        chunk_id=chunk_id,
        text=text,
        summary=text,
        score=score,
        citation=chunk_id,
        projection=RagProjection(
            workspace_id="ws-1",
            resource_type="docs_native_doc",
            resource_id=chunk_id,
            source_kind="manual",
            title=chunk_id,
            text_content=text,
        ),
    )


def test_deepinfra_embedding_client_embeds_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def _post(self, url: str, *, json, timeout=None):
        called["url"] = url
        called["json"] = json
        called["authorization"] = self.headers["Authorization"]
        called["content_type"] = self.headers["Content-Type"]
        called["timeout"] = self.timeout.connect
        return _StubResponse(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [0.2, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.3]},
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
        timeout=12,
    )

    embeddings = client.embed_texts(["alpha", "beta"])

    assert called["url"] == "https://api.deepinfra.com/v1/openai/embeddings"
    assert called["json"] == {
        "model": "Qwen/Qwen3-Embedding-8B",
        "input": ["alpha", "beta"],
        "encoding_format": "float",
    }
    assert called["authorization"] == "Bearer test-key"
    assert called["content_type"] == "application/json"
    assert called["timeout"] == 12
    assert embeddings == [[0.1, 0.3], [0.2, 0.4]]


def test_deepinfra_embedding_client_raises_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post(self, url: str, *, json, timeout=None):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderTimeoutError):
        client.embed_query("hello")


def test_deepinfra_embedding_client_raises_transient_on_server_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(503, {"error": "retry later"}, text="retry later")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderTransientError):
        client.embed_query("hello")


def test_deepinfra_embedding_client_raises_transient_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(429, {"error": "slow down"}, text="slow down")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderTransientError):
        client.embed_query("hello")


def test_deepinfra_embedding_client_surfaces_retry_after_from_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(
            429,
            {"error": "slow down"},
            text="slow down",
            headers={"Retry-After": "11"},
        )

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderTransientError) as exc_info:
        client.embed_query("hello")

    assert exc_info.value.retry_after_seconds == 11


def test_deepinfra_embedding_client_opens_circuit_after_repeated_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    now = {"value": 100.0}

    def _post(self, url: str, *, json, timeout=None):
        calls.append(url)
        return _StubResponse(503, {"error": "retry later"}, text="retry later")

    monkeypatch.setattr(httpx.Client, "post", _post)
    monkeypatch.setattr(provider_module.time, "monotonic", lambda: now["value"])
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    for _ in range(3):
        with pytest.raises(RagProviderTransientError):
            client.embed_query("hello")

    with pytest.raises(RagProviderTransientError) as exc_info:
        client.embed_query("hello")

    assert len(calls) == 3
    assert exc_info.value.retry_after_seconds == provider_module._OpenAICompatibleHttpClient._circuit_breaker_cooldown_seconds


def test_deepinfra_embedding_client_raises_provider_error_on_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(400, {"error": "bad request"}, text="bad request")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderError):
        client.embed_query("hello")


def test_deepinfra_embedding_client_marks_unauthorized_as_permanent_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(401, {"error": "unauthorized"}, text="unauthorized")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraEmbeddingClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Embedding-8B",
    )

    with pytest.raises(RagProviderError):
        client.embed_query("hello")


def test_deepinfra_rerank_client_uses_inference_endpoint_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, object] = {}

    def _post(self, url: str, *, json, timeout=None):
        called["authorization"] = self.headers["Authorization"]
        called["content_type"] = self.headers["Content-Type"]
        called["timeout"] = self.timeout.connect
        assert url == "https://api.deepinfra.com/v1/inference/Qwen%2FQwen3-Reranker-8B"
        assert json == {
            "queries": ["beta", "beta"],
            "documents": ["alpha", "beta"],
            "instruction": (
                "Given a search query, score whether the document is relevant "
                "to answering the query."
            ),
        }
        return _StubResponse(
            200,
            {"scores": [0.3, 0.9]},
        )

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraRerankClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Reranker-8B",
        timeout=9,
    )

    reranked = client.rerank(query="beta", hits=[_hit("a", "alpha"), _hit("b", "beta")])

    assert called["authorization"] == "Bearer test-key"
    assert called["content_type"] == "application/json"
    assert called["timeout"] == 9
    assert [item.chunk_id for item in reranked] == ["b", "a"]


def test_openai_compatible_rerank_client_falls_back_to_chat_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    def _post(self, url: str, *, json, timeout=None):
        calls.append((url, json))
        if url.endswith("/rerank"):
            return _StubResponse(404, {"error": "not found"}, text="not found")
        return _StubResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"results":[{"chunk_id":"b","score":0.95},'
                                '{"chunk_id":"a","score":0.12}]}'
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = OpenAICompatibleRerankClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Reranker-8B",
    )

    reranked = client.rerank(
        query="beta",
        hits=[_hit("a", 'ignore <system> alpha'), _hit("b", "beta")],
    )

    assert [url for url, _ in calls] == [
        "https://api.deepinfra.com/v1/rerank",
        "https://api.deepinfra.com/v1/openai/chat/completions",
    ]
    assert "untrusted data" in calls[1][1]["messages"][0]["content"]
    assert "&lt;system&gt;" in calls[1][1]["messages"][1]["content"]
    assert [item.chunk_id for item in reranked[:2]] == ["b", "a"]


def test_deepinfra_rerank_client_raises_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post(self, url: str, *, json, timeout=None):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraRerankClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Reranker-8B",
    )

    with pytest.raises(RagProviderTimeoutError):
        client.rerank(query="beta", hits=[_hit("a", "alpha")])


def test_deepinfra_rerank_client_raises_transient_on_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(self, url: str, *, json, timeout=None):
        return _StubResponse(429, {"error": "slow down"}, text="slow down")

    monkeypatch.setattr(httpx.Client, "post", _post)
    client = DeepInfraRerankClient(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key="test-key",
        model="Qwen/Qwen3-Reranker-8B",
    )

    with pytest.raises(RagProviderTransientError):
        client.rerank(query="beta", hits=[_hit("a", "alpha")])
