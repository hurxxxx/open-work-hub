"""Anthropic native web-search Adapter for registered PPT research workload."""

from __future__ import annotations

from dataclasses import dataclass
import json

import httpx


@dataclass(frozen=True)
class AnthropicWebResearchResult:
    text: str
    sources: list[dict]


class AnthropicWebResearchAuthenticationError(RuntimeError):
    """Anthropic rejected the configured credential; never include the credential value."""


def run_anthropic_web_research(
    *,
    base_url: str,
    api_key: str,
    model: str,
    research_input: str,
    max_tokens: int,
    max_uses: int = 5,
) -> AnthropicWebResearchResult:
    """Run Anthropic's provider-native web_search tool and normalize citations."""

    payload: dict[str, object] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": (
            "당신은 보고서 작성용 리서치 보조자입니다. 사용자가 준 주제에 대해 웹에서 "
            "최신 정보를 검색해, 발표/보고서에 바로 쓸 핵심 사실·동향·수치를 한국어 "
            "불릿 6~12개로 정리하세요. 추측하거나 확인되지 않은 내용을 만들지 마세요."
        ),
        "messages": [
            {
                "role": "user",
                "content": (
                    f"{research_input}\n\n이 주제로 보고서를 작성하려 합니다. "
                    "웹에서 최신 정보를 검색해 핵심을 정리해 주세요."
                ),
            }
        ],
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_uses,
            }
        ],
        "stream": True,
    }
    if "haiku" not in model.lower():
        payload["output_config"] = {"effort": "low"}

    parts: list[str] = []
    sources: list[dict] = []
    by_url: dict[str, dict] = {}
    tool_input_json: dict[object, str] = {}
    last_query = ""

    def add_source(url: object, title: object, query: str = "") -> None:
        normalized_url = str(url or "").strip()
        if not normalized_url:
            return
        if normalized_url in by_url:
            if query and not by_url[normalized_url].get("query"):
                by_url[normalized_url]["query"] = query
            return
        source = {
            "url": normalized_url,
            "title": str(title or normalized_url).strip(),
        }
        if query:
            source["query"] = query
        by_url[normalized_url] = source
        sources.append(source)

    def add_snippet(url: object, snippet: object) -> None:
        normalized_url = str(url or "").strip()
        normalized_snippet = str(snippet or "").strip()
        if not normalized_url or not normalized_snippet or normalized_url not in by_url:
            return
        if not by_url[normalized_url].get("snippet"):
            by_url[normalized_url]["snippet"] = normalized_snippet[:160]

    timeout = httpx.Timeout(connect=30.0, read=180.0, write=60.0, pool=30.0)
    with httpx.stream(
        "POST",
        base_url.rstrip("/") + "/v1/messages",
        json=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        timeout=timeout,
    ) as response:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                raise AnthropicWebResearchAuthenticationError(
                    "Anthropic research authentication failed"
                ) from exc
            raise
        for line in response.iter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                event = json.loads(data)
            except ValueError:
                continue
            event_type = event.get("type")
            if event_type == "content_block_start":
                block = event.get("content_block") or {}
                index = event.get("index")
                block_type = block.get("type")
                if block_type == "server_tool_use" and block.get("name") == "web_search":
                    tool_input_json[index] = ""
                    tool_input = block.get("input")
                    if isinstance(tool_input, dict) and tool_input.get("query"):
                        last_query = str(tool_input["query"])
                elif block_type == "web_search_tool_result":
                    for item in block.get("content") or []:
                        if isinstance(item, dict) and item.get("type") == "web_search_result":
                            add_source(item.get("url"), item.get("title"), last_query)
            elif event_type == "content_block_delta":
                delta = event.get("delta") or {}
                index = event.get("index")
                delta_type = delta.get("type")
                if delta_type == "text_delta":
                    parts.append(str(delta.get("text") or ""))
                elif delta_type == "input_json_delta" and index in tool_input_json:
                    tool_input_json[index] += str(delta.get("partial_json") or "")
                elif delta_type == "citations_delta":
                    citation = delta.get("citation") or {}
                    add_source(citation.get("url"), citation.get("title"))
                    add_snippet(citation.get("url"), citation.get("cited_text"))
            elif event_type == "content_block_stop":
                index = event.get("index")
                if index in tool_input_json:
                    try:
                        query = json.loads(tool_input_json.pop(index) or "{}").get("query")
                        if query:
                            last_query = str(query)
                    except ValueError:
                        tool_input_json.pop(index, None)
            elif event_type == "error":
                error = event.get("error") or {}
                if error.get("type") == "authentication_error":
                    raise AnthropicWebResearchAuthenticationError(
                        "Anthropic research authentication failed"
                    )
                raise RuntimeError(str(error.get("message") or error))

    return AnthropicWebResearchResult(text="".join(parts).strip(), sources=sources)


__all__ = [
    "AnthropicWebResearchAuthenticationError",
    "AnthropicWebResearchResult",
    "run_anthropic_web_research",
]
