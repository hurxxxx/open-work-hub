from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx

from open_work_hub_api.domains.retrieval.projection_identity import canonical_search_document_id
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclBranch,
    KeywordAclClause,
    KeywordAclFilter,
    KeywordSearchBackendError,
    KeywordSearchHit,
    KeywordSearchQuery,
    KeywordSearchResult,
    KeywordSearchSortSpec,
)
from open_work_hub_api.domains.search.index_gateway import (
    build_bulk_index_ndjson,
    build_partitioned_bulk_index_ndjson,
    bulk_index_error_message,
    keyword_existing_index_mapping_properties,
    keyword_index_definition,
    keyword_partitioned_index_definition,
    keyword_search_index_alias,
    keyword_search_index_name,
    keyword_search_legacy_index_name,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
    keyword_search_versioned_index_name,
    search_index_document_id,
    search_index_document_key,
)
from open_work_hub_api.domains.search.query_policy import KEYWORD_SEARCH_TEXT_FIELDS

MAX_BULK_INDEX_BYTES = 5 * 1024 * 1024
MAX_BULK_INDEX_DOCUMENTS = 500


class OpenSearchError(KeywordSearchBackendError):
    pass


class OpenSearchKeywordClient:
    def __init__(
        self,
        *,
        base_url: str,
        index_prefix: str,
        target_index_name: str | None = None,
        target_schema_version: int = 2,
        partitioned_generation_index: str | None = None,
    ) -> None:
        normalized_partitioned_index = (
            partitioned_generation_index.strip()
            if partitioned_generation_index is not None
            else None
        )
        if target_schema_version == 3:
            if not normalized_partitioned_index:
                raise OpenSearchError(
                    "Partitioned v3 clients require an explicit physical index binding"
                )
            if target_index_name != normalized_partitioned_index:
                raise OpenSearchError(
                    "Partitioned v3 target index must match its physical index binding"
                )
            _validate_partitioned_generation_index(
                index_prefix=index_prefix,
                index_name=normalized_partitioned_index,
            )
        elif normalized_partitioned_index is not None:
            raise OpenSearchError("partitioned_generation_index requires target_schema_version=3")
        self.base_url = base_url.rstrip("/")
        self.index_prefix = index_prefix
        self.index_alias = (
            keyword_search_partitioned_index_alias(index_prefix)
            if target_schema_version == 3
            else keyword_search_index_alias(index_prefix)
        )
        self.legacy_index_name = keyword_search_legacy_index_name(index_prefix)
        self.versioned_index_name = keyword_search_versioned_index_name(index_prefix)
        self.index_name = target_index_name or keyword_search_index_name(index_prefix)
        self._staging = target_index_name is not None
        self._target_schema_version = target_schema_version
        self._partitioned_generation_index = normalized_partitioned_index

    def ensure_index(self) -> None:
        self._require_bound_partitioned_index()
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code == 200:
            if self._partitioned_generation_index is not None:
                self._validate_versioned_index(expected_document_count=None)
                return
            self._request(
                "PUT",
                f"/{self.index_name}/_mapping",
                json={"properties": keyword_existing_index_mapping_properties()},
            )
            return
        if self._staging:
            definition = (
                keyword_partitioned_index_definition()
                if self._target_schema_version == 3
                else keyword_index_definition()
            )
            self._request("PUT", f"/{self.index_name}", json=definition)
            return
        if self._request("HEAD", f"/{self.legacy_index_name}", allow_404=True).status_code == 200:
            self._attach_write_alias(self.legacy_index_name)
            self._request(
                "PUT",
                f"/{self.index_name}/_mapping",
                json={"properties": keyword_existing_index_mapping_properties()},
            )
            return
        if (
            self._request("HEAD", f"/{self.versioned_index_name}", allow_404=True).status_code
            == 200
        ):
            self._attach_write_alias(self.versioned_index_name)
            return
        definition = keyword_index_definition()
        definition["aliases"] = {self.index_alias: {"is_write_index": True}}
        self._request("PUT", f"/{self.versioned_index_name}", json=definition)

    def for_versioned_rebuild(self, *, generation: str) -> OpenSearchKeywordClient:
        """Return a client that writes a clean v2 generation without moving the live alias."""

        return OpenSearchKeywordClient(
            base_url=self.base_url,
            index_prefix=self.index_prefix,
            target_index_name=keyword_search_versioned_index_name(
                self.index_prefix,
                generation=generation,
            ),
        )

    def for_partitioned_rebuild(self, *, generation: str) -> OpenSearchKeywordClient:
        """Return an isolated ADR 0009 v3 client without moving the live alias."""

        physical_index = keyword_search_partitioned_index_name(
            self.index_prefix,
            generation=generation,
        )
        return OpenSearchKeywordClient(
            base_url=self.base_url,
            index_prefix=self.index_prefix,
            target_index_name=physical_index,
            target_schema_version=3,
            partitioned_generation_index=physical_index,
        )

    def activate_versioned_index(
        self,
        *,
        writes_quiesced: bool = False,
        expected_document_count: int | None = None,
        expected_index_uuid: str | None = None,
        expected_config_sha256: str | None = None,
        expected_content_sha256: str | None = None,
    ) -> None:
        """Atomically activate v2 after the caller has stopped every search writer."""

        self._require_bound_partitioned_index()
        if not writes_quiesced:
            raise OpenSearchError(
                "Keyword index activation requires explicit confirmation that search writers "
                "are quiesced"
            )
        if not self._staging:
            raise OpenSearchError("Only a versioned keyword index can be activated")
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code != 200:
            raise OpenSearchError(f"Keyword search index does not exist: {self.index_name}")
        self._validate_versioned_index(expected_document_count=expected_document_count)
        if expected_index_uuid is not None or expected_config_sha256 is not None:
            index_uuid, config_sha256 = self.quality_identity()
            if expected_index_uuid is not None and index_uuid != expected_index_uuid:
                raise OpenSearchError(
                    "Keyword search index identity changed after quality evaluation"
                )
            if expected_config_sha256 is not None and config_sha256 != expected_config_sha256:
                raise OpenSearchError(
                    "Keyword search index configuration changed after quality evaluation"
                )
        if expected_content_sha256 is not None and self.content_sha256() != expected_content_sha256:
            raise OpenSearchError("Keyword search index content changed after quality evaluation")

        self._move_alias_to_index(self.index_name)

    def activate_partitioned_index(
        self,
        *,
        writes_quiesced: bool = False,
        expected_document_count: int | None = None,
        expected_index_uuid: str | None = None,
        expected_config_sha256: str | None = None,
        expected_content_sha256: str | None = None,
    ) -> None:
        """Activate a validated v3 generation using the existing atomic alias move."""

        if self._target_schema_version != 3:
            raise OpenSearchError("Only a partitioned v3 index can use this activation path")
        self.activate_versioned_index(
            writes_quiesced=writes_quiesced,
            expected_document_count=expected_document_count,
            expected_index_uuid=expected_index_uuid,
            expected_config_sha256=expected_config_sha256,
            expected_content_sha256=expected_content_sha256,
        )

    def quality_identity(self) -> tuple[str, str]:
        """Return physical UUID and a stable mapping/settings configuration digest."""

        self._require_bound_partitioned_index()
        payload = self._request("GET", f"/{self.index_name}").json()
        index_payload = payload.get(self.index_name)
        if not isinstance(index_payload, dict):
            raise OpenSearchError(f"Keyword search index identity is invalid: {self.index_name}")
        settings = index_payload.get("settings")
        mappings = index_payload.get("mappings")
        if not isinstance(settings, dict) or not isinstance(mappings, dict):
            raise OpenSearchError(
                f"Keyword search index configuration is invalid: {self.index_name}"
            )
        index_settings = settings.get("index")
        if not isinstance(index_settings, dict):
            raise OpenSearchError(f"Keyword search index settings are invalid: {self.index_name}")
        index_uuid = index_settings.get("uuid")
        if not isinstance(index_uuid, str) or not index_uuid:
            raise OpenSearchError(f"Keyword search index UUID is missing: {self.index_name}")
        stable_index_settings = dict(index_settings)
        for transient_key in ("creation_date", "provided_name", "uuid"):
            stable_index_settings.pop(transient_key, None)
        canonical = json.dumps(
            {
                "mappings": mappings,
                "settings": {**settings, "index": stable_index_settings},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return index_uuid, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def content_sha256(self) -> str:
        """Hash every stored document in stable identity order."""

        self._require_bound_partitioned_index()
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code != 200:
            raise OpenSearchError(f"Keyword search index does not exist: {self.index_name}")
        digest = hashlib.sha256()
        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": MAX_BULK_INDEX_DOCUMENTS,
                "query": {"match_all": {}},
                "sort": [
                    {},
                    {"entity_type": "asc"},
                    {"entity_id": "asc"},
                ],
            }
            if search_after is not None:
                body["search_after"] = search_after
            payload = self._request(
                "POST",
                f"/{self.index_name}/_search",
                json=body,
            ).json()
            hits = payload.get("hits", {}).get("hits", [])
            if not isinstance(hits, list):
                raise OpenSearchError("Keyword index content digest returned invalid hits")
            for hit in hits:
                canonical = json.dumps(
                    {"_id": hit.get("_id"), "_source": hit.get("_source")},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                digest.update(canonical.encode("utf-8"))
                digest.update(b"\n")
            if len(hits) < MAX_BULK_INDEX_DOCUMENTS:
                break
            next_search_after = hits[-1].get("sort")
            if not isinstance(next_search_after, list):
                raise OpenSearchError(
                    "Keyword index content digest is missing a stable search cursor"
                )
            search_after = next_search_after
        return digest.hexdigest()

    def rollback_to_legacy_index(
        self,
        *,
        writes_quiesced: bool = False,
        expected_document_count: int,
    ) -> None:
        """Atomically restore the one canonical legacy v1 index after a count check."""

        if not writes_quiesced:
            raise OpenSearchError(
                "Keyword index rollback requires explicit confirmation that search writers "
                "are quiesced"
            )
        if self._request("HEAD", f"/{self.legacy_index_name}", allow_404=True).status_code != 200:
            raise OpenSearchError(
                f"Legacy keyword search index does not exist: {self.legacy_index_name}"
            )
        count_payload = self._request("GET", f"/{self.legacy_index_name}/_count").json()
        actual_document_count = int(count_payload.get("count") or 0)
        if actual_document_count != expected_document_count:
            raise OpenSearchError(
                "Legacy keyword search index document count mismatch: "
                f"expected={expected_document_count}, actual={actual_document_count}"
            )
        self._move_alias_to_index(self.legacy_index_name)

    def _move_alias_to_index(self, target_index_name: str) -> None:
        response = self._request("GET", f"/_alias/{self.index_alias}", allow_404=True)
        current_indices = sorted(response.json()) if response.status_code == 200 else []
        actions: list[dict[str, Any]] = [
            {"remove": {"index": index_name, "alias": self.index_alias}}
            for index_name in current_indices
            if index_name != target_index_name
        ]
        actions.append(
            {
                "add": {
                    "index": target_index_name,
                    "alias": self.index_alias,
                    "is_write_index": True,
                }
            }
        )
        self._request("POST", "/_aliases", json={"actions": actions})

    def _validate_versioned_index(self, *, expected_document_count: int | None) -> None:
        mapping_payload = self._request("GET", f"/{self.index_name}/_mapping").json()
        index_mapping = mapping_payload.get(self.index_name)
        mappings = index_mapping.get("mappings") if isinstance(index_mapping, dict) else None
        metadata = mappings.get("_meta") if isinstance(mappings, dict) else None
        if (
            not isinstance(metadata, dict)
            or metadata.get("schema_version") != self._target_schema_version
        ):
            raise OpenSearchError(
                f"Keyword search index has an incompatible schema: {self.index_name}"
            )
        count_payload = self._request("GET", f"/{self.index_name}/_count").json()
        actual_document_count = int(count_payload.get("count") or 0)
        if expected_document_count is not None and actual_document_count != expected_document_count:
            raise OpenSearchError(
                "Keyword search index document count mismatch: "
                f"expected={expected_document_count}, actual={actual_document_count}"
            )

    def index_exists(self) -> bool:
        self._require_bound_partitioned_index()
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code == 200:
            return True
        if self._staging:
            return False
        for existing_index_name in (self.legacy_index_name, self.versioned_index_name):
            if (
                self._request(
                    "HEAD",
                    f"/{existing_index_name}",
                    allow_404=True,
                ).status_code
                == 200
            ):
                self._attach_write_alias(existing_index_name)
                return True
        return False

    def count_documents(self) -> int:
        """Return the exact document count for the explicitly bound index."""

        self._require_bound_partitioned_index()
        if self._request("HEAD", f"/{self.index_name}", allow_404=True).status_code != 200:
            raise OpenSearchError(f"Keyword search index does not exist: {self.index_name}")
        payload = self._request("GET", f"/{self.index_name}/_count").json()
        count = payload.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise OpenSearchError("Keyword search index returned an invalid document count")
        return count

    def refresh_partitioned_index(self) -> None:
        """Make completed v3 baseline/replay writes visible to validation reads."""

        self._require_partitioned_staging_client()
        self._request("POST", f"/{self.index_name}/_refresh")

    def rebuild_company_index(self, *, documents: list[dict[str, Any]]) -> None:
        self._require_legacy_mutation_client()
        self.ensure_index()
        if documents:
            self._bulk_index_documents(documents)
            self._delete_stale_documents(
                current_document_ids=[search_index_document_id(document) for document in documents],
            )
        else:
            self._delete_all_documents()
        self._request("POST", f"/{self.index_name}/_refresh")

    def upsert_document(self, document: dict[str, Any]) -> None:
        self._require_legacy_mutation_client()
        self.ensure_index()
        self._request(
            "PUT",
            f"/{self.index_name}/_doc/{search_index_document_id(document)}",
            json=document,
            params={"refresh": "true"},
        )

    def upsert_partitioned_document(self, document: dict[str, Any]) -> str:
        """Write one canonical v3 projection with strict external version ordering."""

        self._require_partitioned_staging_client()
        resource_type, resource_id, projection_version = _partitioned_projection_identity(document)
        self.ensure_index()
        document_id = canonical_search_document_id(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        response = self._request(
            "PUT",
            f"/{self.index_name}/_doc/{document_id}",
            json=document,
            params={
                "refresh": "false",
                "version": projection_version,
                "version_type": "external",
            },
            allow_409=True,
        )
        if response.status_code != 409:
            return "upserted"
        return self._classify_external_version_conflict(
            document_id=document_id,
            projection_version=projection_version,
            deleted_is_idempotent=False,
        )

    def delete_partitioned_document(
        self,
        *,
        resource_type: str,
        resource_id: str,
        projection_version: int,
    ) -> str:
        """Delete one canonical v3 projection while retaining OpenSearch tombstone ordering."""

        self._require_partitioned_staging_client()
        if isinstance(projection_version, bool) or not isinstance(projection_version, int):
            raise ValueError("Partitioned keyword deletes require an integer projection_version")
        if projection_version <= 0:
            raise ValueError("projection_version must be greater than zero")
        self.ensure_index()
        document_id = canonical_search_document_id(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        response = self._request(
            "DELETE",
            f"/{self.index_name}/_doc/{document_id}",
            allow_404=True,
            allow_409=True,
            params={
                "refresh": "false",
                "version": projection_version,
                "version_type": "external",
            },
        )
        if response.status_code in {200, 404}:
            return "deleted"
        return self._classify_external_version_conflict(
            document_id=document_id,
            projection_version=projection_version,
            deleted_is_idempotent=True,
        )

    def bulk_index_partitioned_documents(self, documents: list[dict[str, Any]]) -> None:
        """Baseline/replay helper for an isolated v3 generation."""

        self._require_partitioned_staging_client()
        for document in documents:
            _partitioned_projection_identity(document)
        self.ensure_index()
        for chunk in _bulk_document_chunks(documents, partitioned=True):
            response = self._request(
                "POST",
                "/_bulk",
                content=build_partitioned_bulk_index_ndjson(
                    index_name=self.index_name,
                    documents=chunk,
                ),
                headers={"Content-Type": "application/x-ndjson"},
                params={"refresh": "false"},
            )
            error_message = bulk_index_error_message(response.json())
            if error_message is not None:
                raise OpenSearchError(error_message)

    def delete_document(self, *, entity_type: str, entity_id: str) -> None:
        self._require_legacy_mutation_client()
        self.ensure_index()
        document_id = search_index_document_key(
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self._request(
            "DELETE",
            f"/{self.index_name}/_doc/{document_id}",
            allow_404=True,
            params={"refresh": "true"},
        )

    def count_company_documents(
        self,
        *,
        entity_types: tuple[str, ...] = (),
    ) -> int:
        self._require_legacy_mutation_client()
        query = (
            {"terms": {"entity_type": list(entity_types)}} if entity_types else {"match_all": {}}
        )
        response = self._request(
            "POST",
            f"/{self.index_name}/_count",
            json={"query": query},
        )
        return int(response.json().get("count") or 0)

    def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
        self._require_bound_partitioned_index()
        if self._partitioned_generation_index is not None:
            if query.retrieval_partition_ids is None:
                raise OpenSearchError("Partitioned v3 searches require retrieval_partition_ids")
        elif query.retrieval_partition_ids is not None:
            raise OpenSearchError(
                "Retrieval partition filters require a partitioned v3 generation client"
            )
        request_kwargs: dict[str, Any] = {}
        if query.request_timeout_seconds is not None:
            request_kwargs["request_timeout_seconds"] = query.request_timeout_seconds
        response = self._request(
            "POST",
            "/_search" if query.point_in_time_id is not None else f"/{self.index_name}/_search",
            json=build_keyword_search_opensearch_body(query),
            **request_kwargs,
        )
        return parse_keyword_search_opensearch_response(response.json())

    def open_point_in_time(self, *, keep_alive: str = "1m") -> str:
        self._require_bound_partitioned_index()
        response = self._request(
            "POST",
            f"/{self.index_name}/_search/point_in_time",
            params={"keep_alive": keep_alive},
        )
        point_in_time_id = str(response.json().get("pit_id") or "").strip()
        if not point_in_time_id:
            raise OpenSearchError("OpenSearch point-in-time response is missing pit_id")
        return point_in_time_id

    def close_point_in_time(self, point_in_time_id: str) -> None:
        normalized = str(point_in_time_id or "").strip()
        if not normalized:
            raise ValueError("point_in_time_id is required")
        self._request(
            "DELETE",
            "/_search/point_in_time",
            json={"pit_id": [normalized]},
        )

    def _bulk_index_documents(self, documents: list[dict[str, Any]]) -> None:
        self._require_legacy_mutation_client()
        for chunk in _bulk_document_chunks(documents):
            response = self._request(
                "POST",
                "/_bulk",
                content=build_bulk_index_ndjson(index_name=self.index_name, documents=chunk),
                headers={"Content-Type": "application/x-ndjson"},
                params={"refresh": "false"},
            )
            error_message = bulk_index_error_message(response.json())
            if error_message is not None:
                raise OpenSearchError(error_message)

    def _delete_all_documents(
        self,
    ) -> None:
        self._require_legacy_mutation_client()
        self._request(
            "POST",
            f"/{self.index_name}/_delete_by_query",
            json={"query": {"match_all": {}}},
            params={"refresh": "false", "conflicts": "proceed"},
        )

    def _delete_stale_documents(
        self,
        *,
        current_document_ids: list[str],
    ) -> None:
        self._require_legacy_mutation_client()
        self._request(
            "POST",
            f"/{self.index_name}/_delete_by_query",
            json={
                "query": {
                    "bool": {
                        "must_not": [{"ids": {"values": current_document_ids}}],
                    }
                }
            },
            params={"refresh": "false", "conflicts": "proceed"},
        )

    def _attach_write_alias(self, index_name: str) -> None:
        self._request(
            "POST",
            "/_aliases",
            json={
                "actions": [
                    {
                        "add": {
                            "index": index_name,
                            "alias": self.index_alias,
                            "is_write_index": True,
                        }
                    }
                ]
            },
        )

    def _require_partitioned_staging_client(self) -> None:
        if (
            not self._staging
            or self._target_schema_version != 3
            or self._partitioned_generation_index is None
        ):
            raise OpenSearchError(
                "Partitioned projection writes require an isolated v3 generation client"
            )
        self._require_bound_partitioned_index()

    def _require_bound_partitioned_index(self) -> None:
        if self._partitioned_generation_index is None:
            return
        if self.index_name != self._partitioned_generation_index:
            raise OpenSearchError(
                "Partitioned v3 client is bound to physical index "
                f"{self._partitioned_generation_index!r}, not {self.index_name!r}"
            )

    def _require_legacy_mutation_client(self) -> None:
        self._require_bound_partitioned_index()
        if self._partitioned_generation_index is not None:
            raise OpenSearchError(
                "Legacy keyword mutation APIs cannot write a partitioned v3 generation"
            )

    def _classify_external_version_conflict(
        self,
        *,
        document_id: str,
        projection_version: int,
        deleted_is_idempotent: bool,
    ) -> str:
        current = self._request(
            "GET",
            f"/{self.index_name}/_doc/{document_id}",
            allow_404=True,
        )
        if current.status_code == 404:
            if deleted_is_idempotent:
                return "unchanged"
            # A version-conflict response proves that OpenSearch still knows a
            # version at least as new as this write. Realtime GET intentionally
            # hides deleted documents and does not expose the retained external
            # version, so the only safe classification is a newer tombstone.
            # Treat it as superseded to stop retries from outliving gc_deletes
            # and later recreating a resource with stale content.
            return "superseded"
        current_version = int(current.json().get("_version") or 0)
        if current_version == projection_version:
            return "unchanged"
        if current_version > projection_version:
            return "superseded"
        raise OpenSearchError(
            "OpenSearch external version conflict is inconsistent with the stored version"
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        allow_404: bool = False,
        allow_409: bool = False,
        request_timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                timeout=request_timeout_seconds or 15.0,
                **kwargs,
            )
        except httpx.HTTPError as error:
            raise OpenSearchError(f"OpenSearch is unavailable: {error}") from error
        if allow_404 and response.status_code == 404:
            return response
        if allow_409 and response.status_code == 409:
            return response
        if response.status_code >= 400:
            raise OpenSearchError(
                f"OpenSearch request failed ({response.status_code}): {response.text[:500]}"
            )
        return response


def _bulk_document_chunks(
    documents: list[dict[str, Any]],
    *,
    max_bytes: int = MAX_BULK_INDEX_BYTES,
    max_documents: int = MAX_BULK_INDEX_DOCUMENTS,
    partitioned: bool = False,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_bytes = 0
    for document in documents:
        builder = build_partitioned_bulk_index_ndjson if partitioned else build_bulk_index_ndjson
        document_bytes = len(
            builder(index_name="_size_estimate", documents=[document]).encode("utf-8")
        )
        if current and (
            current_bytes + document_bytes > max_bytes or len(current) >= max_documents
        ):
            chunks.append(current)
            current = []
            current_bytes = 0
        current.append(document)
        current_bytes += document_bytes
    if current:
        chunks.append(current)
    return chunks


def _validate_partitioned_generation_index(*, index_prefix: str, index_name: str) -> None:
    physical_prefix = f"{keyword_search_index_alias(index_prefix)}_v3_"
    if not index_name.startswith(physical_prefix):
        raise OpenSearchError("Partitioned v3 clients must bind to a generated physical v3 index")
    generation = index_name.removeprefix(physical_prefix)
    try:
        expected_index_name = keyword_search_partitioned_index_name(
            index_prefix,
            generation=generation,
        )
    except ValueError as error:
        raise OpenSearchError(
            "Partitioned v3 clients must bind to a generated physical v3 index"
        ) from error
    if index_name != expected_index_name:
        raise OpenSearchError("Partitioned v3 clients must bind to a generated physical v3 index")


def _partitioned_projection_identity(document: dict[str, Any]) -> tuple[str, str, int]:
    resource_type = str(document.get("resource_type") or "").strip()
    resource_id = str(document.get("entity_id") or "").strip()
    partition_id = str(document.get("retrieval_partition_id") or "").strip()
    projection_version = document.get("projection_version")
    if not resource_type or not resource_id or not partition_id:
        raise ValueError(
            "Partitioned keyword projections require resource_type, entity_id, and "
            "retrieval_partition_id"
        )
    if isinstance(projection_version, bool) or not isinstance(projection_version, int):
        raise ValueError("Partitioned keyword projections require an integer projection_version")
    if projection_version <= 0:
        raise ValueError("projection_version must be greater than zero")
    return resource_type, resource_id, projection_version


def build_keyword_search_opensearch_body(query: KeywordSearchQuery) -> dict[str, Any]:
    body: dict[str, Any] = {
        "track_total_hits": True,
        "query": build_keyword_search_opensearch_query(query),
        "sort": build_keyword_search_opensearch_sort(query.sort),
        "size": query.size,
    }
    if query.search_after:
        body["search_after"] = list(query.search_after)
    if query.point_in_time_id is not None:
        body["pit"] = {
            "id": query.point_in_time_id,
            "keep_alive": query.point_in_time_keep_alive,
        }
        body["sort"].append({"_shard_doc": {"order": "asc"}})
    return body


def build_keyword_search_opensearch_query(query: KeywordSearchQuery) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if query.retrieval_partition_ids is not None:
        filters.append({"terms": {"retrieval_partition_id": list(query.retrieval_partition_ids)}})
    if query.entity_types:
        filters.append({"terms": {"entity_type": list(query.entity_types)}})
    if query.acl_filter is not None:
        filters.append(keyword_acl_filter_to_opensearch(query.acl_filter))
    if query.dataset_id:
        filters.append(_dataset_filter(query.dataset_id, query.include_missing_dataset))
    if query.people.user_ids:
        filters.append({"terms": {"people.user_id": list(query.people.user_ids)}})
        if query.people.role != "any":
            # ``people`` is not nested. This role clause is only a safe superset
            # pushdown; source rows are still correlated by role/user post-query.
            filters.append({"term": {"people.role": query.people.role}})
    for entity_type, statuses in query.status_by_type:
        if not statuses:
            continue
        filters.append(
            {
                "bool": {
                    "should": [
                        {"bool": {"must_not": [{"term": {"entity_type": entity_type}}]}},
                        {"terms": {"status": list(statuses)}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if query.target_keys:
        filters.append({"terms": {"target_keys": list(query.target_keys)}})
    filters.extend(
        {"terms": {"target_keys": list(group)}} for group in query.target_key_groups if group
    )
    for date_filter in query.date_filters:
        bounds = {
            key: value
            for key, value in {
                "gte": date_filter.from_value,
                "lte": date_filter.to_value,
            }.items()
            if value is not None
        }
        if bounds:
            backend_field = {
                "updated_at": "source_updated_at",
                "created_at": "created_at",
            }.get(date_filter.field, f"date_markers.{date_filter.field}")
            filters.append({"range": {backend_field: bounds}})

    if not query.text.strip():
        return {"bool": {"filter": filters, "must": [{"match_all": {}}]}}

    base_match = {
        "multi_match": {
            "query": query.text.strip(),
            "fields": list(KEYWORD_SEARCH_TEXT_FIELDS),
            "operator": query.text_operator,
            "type": "best_fields",
        }
    }
    if query.text_minimum_should_match is not None:
        base_match["multi_match"]["minimum_should_match"] = query.text_minimum_should_match
    if not query.phrase_match_fields:
        return {"bool": {"filter": filters, "must": [base_match]}}

    return {
        "bool": {
            "filter": filters,
            "should": [
                base_match,
                {
                    "multi_match": {
                        "query": query.text.strip(),
                        "fields": list(query.phrase_match_fields),
                        "type": "phrase",
                        "boost": query.phrase_boost,
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def build_keyword_search_opensearch_sort(
    sort_specs: tuple[KeywordSearchSortSpec, ...],
) -> list[dict[str, Any]]:
    specs = sort_specs or (
        KeywordSearchSortSpec(field="score", direction="desc"),
        KeywordSearchSortSpec(
            field="source_updated_at",
            direction="desc",
            unmapped_type="date",
        ),
    )
    return [_sort_spec_to_opensearch(spec) for spec in specs]


def keyword_acl_filter_to_opensearch(acl_filter: KeywordAclFilter) -> dict[str, Any]:
    if not acl_filter.branches:
        return {"match_none": {}}
    return {
        "bool": {
            "should": [keyword_acl_branch_to_opensearch(branch) for branch in acl_filter.branches],
            "minimum_should_match": 1,
        }
    }


def keyword_acl_branch_to_opensearch(branch: KeywordAclBranch) -> dict[str, Any]:
    return {
        "bool": {
            "filter": [{"term": {"entity_type": branch.entity_type}}],
            "should": [keyword_acl_clause_to_opensearch(clause) for clause in branch.clauses]
            or [{"match_none": {}}],
            "minimum_should_match": 1,
        }
    }


def keyword_acl_clause_to_opensearch(clause: KeywordAclClause) -> dict[str, Any]:
    values = list(clause.values)
    if not values:
        return {"match_none": {}}
    if len(values) == 1:
        return {"term": {clause.field: values[0]}}
    return {"terms": {clause.field: values}}


def parse_keyword_search_opensearch_response(payload: dict[str, Any]) -> KeywordSearchResult:
    hits: list[KeywordSearchHit] = []
    for hit in payload.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source") or {})
        sort_values = hit.get("sort")
        hits.append(
            KeywordSearchHit(
                document=source,
                score=float(hit.get("_score") or 0.0),
                sort_values=tuple(sort_values) if isinstance(sort_values, list) else (),
            )
        )
    return KeywordSearchResult(hits=tuple(hits))


def _dataset_filter(dataset_id: str, include_missing_dataset: bool) -> dict[str, Any]:
    if not include_missing_dataset:
        return {"term": {"dataset_id": dataset_id}}
    return {
        "bool": {
            "should": [
                {"term": {"dataset_id": dataset_id}},
                {"bool": {"must_not": [{"exists": {"field": "dataset_id"}}]}},
            ],
            "minimum_should_match": 1,
        }
    }


def _sort_spec_to_opensearch(spec: KeywordSearchSortSpec) -> dict[str, Any]:
    field = "_score" if spec.field == "score" else spec.field
    payload: dict[str, Any] = {"order": spec.direction}
    if spec.unmapped_type:
        payload["unmapped_type"] = spec.unmapped_type
    return {field: payload}
