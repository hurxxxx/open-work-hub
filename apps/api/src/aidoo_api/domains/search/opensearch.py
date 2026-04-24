from __future__ import annotations

from typing import Any

import httpx


class OpenSearchError(RuntimeError):
    pass


class OpenSearchKeywordClient:
    def __init__(self, *, base_url: str, index_prefix: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.index_name = f"{index_prefix}_keyword_search_documents_v1"

    def ensure_index(self) -> None:
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code == 200:
            self._request("PUT", f"/{self.index_name}/_mapping", json={"properties": _acl_properties()})
            return
        self._request("PUT", f"/{self.index_name}", json=_index_definition())

    def rebuild_workspace(self, *, workspace_id: str, documents: list[dict[str, Any]]) -> None:
        self.ensure_index()
        self._request(
            "POST",
            f"/{self.index_name}/_delete_by_query",
            json={"query": {"term": {"workspace_id": workspace_id}}},
            params={"refresh": "true", "conflicts": "proceed"},
        )
        if not documents:
            return
        lines: list[str] = []
        for document in documents:
            document_id = f"{document['workspace_id']}:{document['entity_type']}:{document['entity_id']}"
            lines.append(_json_dumps({"index": {"_index": self.index_name, "_id": document_id}}))
            lines.append(_json_dumps(document))
        body = "\n".join(lines) + "\n"
        response = self._request(
            "POST",
            "/_bulk",
            content=body,
            headers={"Content-Type": "application/x-ndjson"},
            params={"refresh": "true"},
        )
        payload = response.json()
        if payload.get("errors"):
            raise OpenSearchError(f"OpenSearch bulk indexing failed: {str(payload)[:500]}")

    def search(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"/{self.index_name}/_search", json=body)
        return response.json()

    def _request(
        self,
        method: str,
        path: str,
        *,
        allow_404: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = httpx.request(method, f"{self.base_url}{path}", timeout=15.0, **kwargs)
        except httpx.HTTPError as error:
            raise OpenSearchError(f"OpenSearch is unavailable: {error}") from error
        if allow_404 and response.status_code == 404:
            return response
        if response.status_code >= 400:
            raise OpenSearchError(f"OpenSearch request failed ({response.status_code}): {response.text[:500]}")
        return response


def _index_definition() -> dict[str, Any]:
    return {
        "settings": {
            "analysis": {
                "tokenizer": {
                    "korean_ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 3,
                        "token_chars": ["letter", "digit"],
                    }
                },
                "analyzer": {
                    "korean_ngram": {
                        "type": "custom",
                        "tokenizer": "korean_ngram_tokenizer",
                        "filter": ["lowercase"],
                    }
                },
            }
        },
        "mappings": {
            "dynamic": "false",
            "properties": {
                "workspace_id": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "entity_id": {"type": "keyword"},
                **_acl_properties(),
                "title": {
                    "type": "text",
                    "analyzer": "korean_ngram",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "summary": {"type": "text", "analyzer": "korean_ngram"},
                "body": {"type": "text", "analyzer": "korean_ngram"},
                "keywords": {"type": "text", "analyzer": "korean_ngram"},
                "search_text": {"type": "text", "analyzer": "korean_ngram"},
                "status": {"type": "keyword"},
                "status_label": {"type": "keyword"},
                "visibility": {"type": "keyword"},
                "people": {
                    "properties": {
                        "role": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "label": {"type": "keyword"},
                    }
                },
                "containers": {
                    "properties": {
                        "type": {"type": "keyword"},
                        "id": {"type": "keyword"},
                        "label": {"type": "keyword"},
                    }
                },
                "container_keys": {"type": "keyword"},
                "date_markers": {"type": "object", "dynamic": "true"},
                "deep_link": {"type": "keyword"},
                "preview_url": {"type": "keyword"},
                "metadata": {"type": "object", "enabled": True},
                "rank_boost": {"type": "float"},
                "source_updated_at": {"type": "date"},
                "created_at": {"type": "date"},
            },
        },
    }


def _acl_properties() -> dict[str, Any]:
    return {
        "owner_user_id": {"type": "keyword"},
        "team_ids": {"type": "keyword"},
        "participant_user_ids": {"type": "keyword"},
        "shared_user_ids": {"type": "keyword"},
        "granted_user_ids": {"type": "keyword"},
    }


def _json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
