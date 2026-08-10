from __future__ import annotations

import json

import httpx
import pytest

from open_alm_api.domains.ppt_generator import anthropic_search_adapter as adapter


def test_anthropic_ppt_research_keeps_native_web_search_and_citations(monkeypatch) -> None:
    captured: dict[str, object] = {}
    events = [
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "server_tool_use",
                "name": "web_search",
                "input": {"query": "battery trend"},
            },
        },
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "web_search_tool_result",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://example.com/report",
                        "title": "Example Report",
                    }
                ],
            },
        },
        {
            "type": "content_block_delta",
            "index": 2,
            "delta": {"type": "text_delta", "text": "핵심 동향"},
        },
        {
            "type": "content_block_delta",
            "index": 2,
            "delta": {
                "type": "citations_delta",
                "citation": {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "cited_text": "evidence",
                },
            },
        },
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_lines(self):
            return [f"data: {json.dumps(event)}" for event in events]

    def fake_stream(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(adapter.httpx, "stream", fake_stream)

    result = adapter.run_anthropic_web_research(
        base_url="https://api.anthropic.com",
        api_key="secret",
        model="claude-sonnet-4-6",
        research_input="주제: 배터리 동향",
        max_tokens=1024,
        max_uses=4,
    )

    assert result.text == "핵심 동향"
    assert result.sources == [
        {
            "url": "https://example.com/report",
            "title": "Example Report",
            "query": "battery trend",
            "snippet": "evidence",
        }
    ]
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["json"]["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}
    ]
    assert captured["json"]["max_tokens"] == 1024


def test_anthropic_ppt_research_normalizes_unauthorized_response(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr(adapter.httpx, "stream", lambda *_args, **_kwargs: FakeResponse())

    with pytest.raises(adapter.AnthropicWebResearchAuthenticationError):
        adapter.run_anthropic_web_research(
            base_url="https://api.anthropic.com",
            api_key="invalid",
            model="claude-sonnet-4-6",
            research_input="topic",
            max_tokens=1024,
        )
