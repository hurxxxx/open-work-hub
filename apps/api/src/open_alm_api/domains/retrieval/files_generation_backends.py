from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

from open_alm_api.domains.rag.providers.qdrant import QdrantVectorIndexClient
from open_alm_api.domains.rag.runtime import (
    get_default_embedding_dimensions,
    resolve_default_collection_name,
    resolve_partitioned_rag_collection_alias,
)
from open_alm_api.domains.retrieval.files_generation_runner import (
    FilesBackendPairInspection,
    FilesGenerationPairSpec,
    FilesGenerationRuntimeSettings,
    FilesPhysicalProjectionInventory,
    ProjectionContractDigest,
    opensearch_projection_contract_bytes,
    projection_inventory_identity_sha256,
    qdrant_projection_contract_bytes,
)
from open_alm_api.domains.retrieval.models import RetrievalProjectionBackend
from open_alm_api.domains.retrieval.projection_identity import (
    canonical_search_document_id,
    canonical_vector_point_id,
)
from open_alm_api.domains.search.backend_factory import (
    build_partitioned_keyword_search_client,
)
from open_alm_api.domains.search.index_gateway import (
    keyword_search_index_alias,
    keyword_search_partitioned_index_alias,
)
from open_alm_api.domains.search.opensearch import OpenSearchKeywordClient
from open_alm_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


@dataclass(frozen=True, slots=True)
class FilesPhysicalResourcePresence:
    opensearch_documents: int
    qdrant_points: int


class FilesPhysicalGenerationBackends:
    """Physical OpenSearch v3 and Qdrant v1 generation control plane.

    Application reads and writes remain bound to physical names. Aliases exist
    only as dedicated operational pointers; this class refuses the legacy
    aliases used by non-Files traffic.
    """

    def __init__(
        self,
        settings: FilesGenerationRuntimeSettings,
        *,
        qdrant_client: QdrantClient | None = None,
        embedding_dimensions_resolver=get_default_embedding_dimensions,
    ) -> None:
        if str(settings.keyword_search_backend or "").strip().lower() != "opensearch":
            raise ValueError("Files generation management requires OpenSearch")
        if str(settings.rag_vector_index_provider or "").strip().lower() != "qdrant":
            raise ValueError("Files generation management requires Qdrant")
        self._settings = settings
        self._owns_qdrant_client = qdrant_client is None
        self._qdrant = qdrant_client or QdrantClient(
            url=settings.rag_qdrant_url,
            api_key=str(settings.rag_qdrant_api_key or "").strip() or None,
            timeout=30,
        )
        self._embedding_dimensions_resolver = embedding_dimensions_resolver

    def close(self) -> None:
        if self._owns_qdrant_client:
            self._qdrant.close()

    def inspect_pair(self, spec: FilesGenerationPairSpec) -> FilesBackendPairInspection:
        self._require_physical_names_not_aliases(spec)
        opensearch = self._inspect_opensearch(spec)
        qdrant = self._inspect_qdrant(spec)
        return FilesBackendPairInspection(opensearch=opensearch, qdrant=qdrant)

    def count_resource_presence(
        self,
        spec: FilesGenerationPairSpec,
        *,
        resource_ids: list[str] | tuple[str, ...],
    ) -> FilesPhysicalResourcePresence:
        """Count a bounded resource cohort directly in both physical backends."""

        normalized_ids = tuple(
            sorted({str(resource_id or "").strip() for resource_id in resource_ids})
        )
        if any(not resource_id for resource_id in normalized_ids):
            raise ValueError("Files resource IDs must be non-empty")
        if not normalized_ids:
            return FilesPhysicalResourcePresence(0, 0)
        self._require_physical_names_not_aliases(spec)
        if not self._opensearch_client(spec.opensearch_physical_name).index_exists():
            raise RuntimeError("OpenSearch physical generation is missing")
        if not self._qdrant.collection_exists(collection_name=spec.qdrant_physical_name):
            raise RuntimeError("Qdrant physical generation is missing")

        opensearch_documents = 0
        qdrant_points = 0
        for offset in range(0, len(normalized_ids), 100):
            batch = normalized_ids[offset : offset + 100]
            response = self._opensearch_request(
                "POST",
                f"/{quote(spec.opensearch_physical_name, safe='')}/_count",
                json={
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"resource_type": FILE_MANAGER_FILE_RESOURCE_TYPE}},
                                {"terms": {"entity_id": list(batch)}},
                            ]
                        }
                    }
                },
            ).json()
            opensearch_documents += int(response.get("count", 0))
            qdrant_points += int(
                self._qdrant.count(
                    collection_name=spec.qdrant_physical_name,
                    count_filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="resource_type",
                                match=models.MatchValue(value=FILE_MANAGER_FILE_RESOURCE_TYPE),
                            ),
                            models.FieldCondition(
                                key="resource_id",
                                match=models.MatchAny(any=list(batch)),
                            ),
                        ]
                    ),
                    exact=True,
                ).count
            )
        return FilesPhysicalResourcePresence(
            opensearch_documents=opensearch_documents,
            qdrant_points=qdrant_points,
        )

    def _require_physical_names_not_aliases(self, spec: FilesGenerationPairSpec) -> None:
        opensearch_alias = self._opensearch_request(
            "GET",
            f"/_alias/{quote(spec.opensearch_physical_name, safe='')}",
            allow_404=True,
        )
        if opensearch_alias.status_code != 404:
            raise RuntimeError("OpenSearch physical generation name is an alias")
        if any(
            str(alias.alias_name) == spec.qdrant_physical_name
            for alias in self._qdrant.get_aliases().aliases
        ):
            raise RuntimeError("Qdrant physical generation name is an alias")

    def prepare_empty_pair(self, spec: FilesGenerationPairSpec) -> None:
        opensearch = self._opensearch_client(spec.opensearch_physical_name)
        opensearch.ensure_index()
        dimensions = int(self._embedding_dimensions_resolver())
        vector_index = QdrantVectorIndexClient(
            client=self._qdrant,
            partitioned_generation=True,
            generation_collection=spec.qdrant_physical_name,
        )
        vector_index.ensure_collection(
            collection=spec.qdrant_physical_name,
            dense_dimensions=dimensions,
            sparse_enabled=True,
        )

    def alias_target(self, *, backend: str, alias_name: str) -> str | None:
        self._require_dedicated_alias(backend=backend, alias_name=alias_name)
        if backend == RetrievalProjectionBackend.OPENSEARCH.value:
            response = self._opensearch_request(
                "GET",
                f"/_alias/{quote(alias_name, safe='')}",
                allow_404=True,
            )
            if response.status_code == 404:
                return None
            targets = tuple(sorted(str(name) for name in response.json()))
        elif backend == RetrievalProjectionBackend.QDRANT.value:
            targets = tuple(
                sorted(
                    str(alias.collection_name)
                    for alias in self._qdrant.get_aliases().aliases
                    if str(alias.alias_name) == alias_name
                )
            )
        else:
            raise ValueError("Unsupported retrieval projection backend")
        if len(targets) > 1:
            raise RuntimeError("Dedicated retrieval alias has multiple targets")
        return targets[0] if targets else None

    def set_alias(self, *, backend: str, alias_name: str, physical_name: str) -> None:
        self._require_dedicated_alias(backend=backend, alias_name=alias_name)
        self._require_physical_name(
            backend=backend,
            alias_name=alias_name,
            physical_name=physical_name,
        )
        current = self.alias_target(backend=backend, alias_name=alias_name)
        if current == physical_name:
            return
        if backend == RetrievalProjectionBackend.OPENSEARCH.value:
            if not self._opensearch_client(physical_name).index_exists():
                raise RuntimeError("OpenSearch target generation is missing")
            actions: list[dict[str, Any]] = []
            if current is not None:
                actions.append({"remove": {"index": current, "alias": alias_name}})
            actions.append(
                {
                    "add": {
                        "index": physical_name,
                        "alias": alias_name,
                        "is_write_index": True,
                    }
                }
            )
            self._opensearch_request("POST", "/_aliases", json={"actions": actions})
            return
        if backend == RetrievalProjectionBackend.QDRANT.value:
            if not self._qdrant.collection_exists(collection_name=physical_name):
                raise RuntimeError("Qdrant target generation is missing")
            operations: list[models.CreateAliasOperation | models.DeleteAliasOperation] = []
            if current is not None:
                operations.append(
                    models.DeleteAliasOperation(
                        delete_alias=models.DeleteAlias(alias_name=alias_name)
                    )
                )
            operations.append(
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=physical_name,
                        alias_name=alias_name,
                    )
                )
            )
            self._qdrant.update_collection_aliases(
                change_aliases_operations=operations,
                timeout=30,
            )
            return
        raise ValueError("Unsupported retrieval projection backend")

    def remove_alias(self, *, backend: str, alias_name: str) -> None:
        self._require_dedicated_alias(backend=backend, alias_name=alias_name)
        current = self.alias_target(backend=backend, alias_name=alias_name)
        if current is None:
            return
        if backend == RetrievalProjectionBackend.OPENSEARCH.value:
            self._opensearch_request(
                "POST",
                "/_aliases",
                json={"actions": [{"remove": {"index": current, "alias": alias_name}}]},
            )
            return
        if backend == RetrievalProjectionBackend.QDRANT.value:
            self._qdrant.update_collection_aliases(
                change_aliases_operations=[
                    models.DeleteAliasOperation(
                        delete_alias=models.DeleteAlias(alias_name=alias_name)
                    )
                ],
                timeout=30,
            )
            return
        raise ValueError("Unsupported retrieval projection backend")

    def _inspect_opensearch(
        self,
        spec: FilesGenerationPairSpec,
    ) -> FilesPhysicalProjectionInventory | None:
        client = self._opensearch_client(spec.opensearch_physical_name)
        if not client.index_exists():
            return None
        document_count = client.count_documents()
        physical_id, config_sha256 = client.quality_identity()
        content_sha256 = client.content_sha256()
        identities, projection_sha256 = self._opensearch_projection_inventory(
            spec.opensearch_physical_name
        )
        if len(identities) != document_count:
            raise RuntimeError("OpenSearch projection inventory count is inconsistent")
        return FilesPhysicalProjectionInventory(
            resource_count=len(identities),
            record_count=document_count,
            identity_sha256=projection_inventory_identity_sha256(identities),
            content_sha256=content_sha256,
            config_sha256=config_sha256,
            physical_id=physical_id,
            projection_sha256=projection_sha256,
        )

    def _inspect_qdrant(
        self,
        spec: FilesGenerationPairSpec,
    ) -> FilesPhysicalProjectionInventory | None:
        collection = spec.qdrant_physical_name
        if not self._qdrant.collection_exists(collection_name=collection):
            return None
        info = self._qdrant.get_collection(collection_name=collection)
        config_sha256 = _canonical_sha256(
            {
                "params": _jsonable(info.config.params),
                # Qdrant reports the current number of indexed points alongside
                # the immutable payload-index definition.  Point counts change
                # during ordinary writes and therefore must not invalidate the
                # generation configuration identity.
                "payload_schema": _qdrant_payload_schema_config(info.payload_schema),
            }
        )
        exact_count = int(
            self._qdrant.count(
                collection_name=collection,
                count_filter=None,
                exact=True,
            ).count
        )
        identities: set[tuple[str, str, int]] = set()
        content_digest = _OrderIndependentDigest()
        projection_digest = ProjectionContractDigest()
        offset: int | str | None = None
        scanned = 0
        while True:
            records, offset = self._qdrant.scroll(
                collection_name=collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for record in records:
                payload = dict(record.payload or {})
                identity = _projection_identity_from_payload(payload)
                chunk_id = str(payload.get("chunk_id") or "").strip()
                if not chunk_id:
                    raise RuntimeError("Qdrant projection contains a blank chunk identity")
                expected_point_id = canonical_vector_point_id(
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id=identity[0],
                    chunk_id=chunk_id,
                )
                if str(record.id).strip().lower() != expected_point_id:
                    raise RuntimeError("Qdrant projection point identity is not canonical")
                identities.add(identity)
                content_digest.add(
                    _canonical_json_bytes(
                        {
                            "id": str(record.id),
                            "payload": payload,
                            "vector": _jsonable(record.vector),
                        }
                    )
                )
                projection_digest.add(
                    qdrant_projection_contract_bytes(
                        point_id=str(record.id).strip().lower(),
                        payload=payload,
                    )
                )
                scanned += 1
            if offset is None:
                break
        if scanned != exact_count:
            raise RuntimeError("Qdrant projection inventory count is inconsistent")
        return FilesPhysicalProjectionInventory(
            resource_count=len(identities),
            record_count=exact_count,
            identity_sha256=projection_inventory_identity_sha256(identities),
            content_sha256=content_digest.hexdigest(),
            config_sha256=config_sha256,
            physical_id=collection,
            projection_sha256=projection_digest.hexdigest(),
        )

    def _opensearch_projection_identities(
        self,
        physical_name: str,
    ) -> set[tuple[str, str, int]]:
        identities, _projection_sha256 = self._opensearch_projection_inventory(physical_name)
        return identities

    def _opensearch_projection_inventory(
        self,
        physical_name: str,
    ) -> tuple[set[tuple[str, str, int]], str]:
        identities: set[tuple[str, str, int]] = set()
        projection_digest = ProjectionContractDigest()
        search_after: list[Any] | None = None
        while True:
            body: dict[str, Any] = {
                "size": 500,
                "query": {"match_all": {}},
                "sort": [{"resource_type": "asc"}, {"entity_id": "asc"}],
                "_source": True,
            }
            if search_after is not None:
                body["search_after"] = search_after
            payload = self._opensearch_request(
                "POST",
                f"/{quote(physical_name, safe='')}/_search",
                json=body,
            ).json()
            hits = payload.get("hits", {}).get("hits", [])
            if not isinstance(hits, list):
                raise RuntimeError("OpenSearch projection inventory is invalid")
            for hit in hits:
                source = hit.get("_source") if isinstance(hit, dict) else None
                if not isinstance(source, dict):
                    raise RuntimeError("OpenSearch projection source is invalid")
                identity = _projection_identity_from_payload(source)
                expected_document_id = canonical_search_document_id(
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id=identity[0],
                )
                if str(hit.get("_id") or "").strip().lower() != expected_document_id:
                    raise RuntimeError("OpenSearch projection document identity is not canonical")
                identities.add(identity)
                projection_digest.add(
                    opensearch_projection_contract_bytes(
                        document_id=expected_document_id,
                        document=source,
                    )
                )
            if len(hits) < 500:
                break
            cursor = hits[-1].get("sort")
            if not isinstance(cursor, list):
                raise RuntimeError("OpenSearch projection cursor is invalid")
            search_after = cursor
        return identities, projection_digest.hexdigest()

    def _opensearch_client(self, physical_name: str) -> OpenSearchKeywordClient:
        client = build_partitioned_keyword_search_client(
            self._settings,
            physical_index_name=physical_name,
        )
        if not isinstance(client, OpenSearchKeywordClient):
            raise RuntimeError("Partitioned keyword backend is not OpenSearch")
        return client

    def _require_dedicated_alias(self, *, backend: str, alias_name: str) -> None:
        if backend == RetrievalProjectionBackend.OPENSEARCH.value:
            expected = keyword_search_partitioned_index_alias(
                self._settings.opensearch_index_prefix
            )
            forbidden = keyword_search_index_alias(self._settings.opensearch_index_prefix)
        elif backend == RetrievalProjectionBackend.QDRANT.value:
            expected = resolve_partitioned_rag_collection_alias(self._settings)
            forbidden = resolve_default_collection_name(self._settings)
        else:
            raise ValueError("Unsupported retrieval projection backend")
        if alias_name != expected or alias_name == forbidden:
            raise ValueError("Only the dedicated partitioned retrieval alias may be changed")

    def _require_physical_name(
        self,
        *,
        backend: str,
        alias_name: str,
        physical_name: str,
    ) -> None:
        if backend == RetrievalProjectionBackend.OPENSEARCH.value:
            prefix = f"{alias_name}_"
        elif backend == RetrievalProjectionBackend.QDRANT.value:
            prefix = f"{alias_name}-"
        else:
            raise ValueError("Unsupported retrieval projection backend")
        if not physical_name.startswith(prefix):
            raise ValueError("Alias target is not a partitioned physical generation")

    def _opensearch_request(
        self,
        method: str,
        path: str,
        *,
        allow_404: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        response = httpx.request(
            method,
            f"{self._settings.opensearch_url.rstrip('/')}{path}",
            timeout=30,
            **kwargs,
        )
        if allow_404 and response.status_code == 404:
            return response
        response.raise_for_status()
        return response


class _OrderIndependentDigest:
    _MODULUS = 1 << 256

    def __init__(self) -> None:
        self._count = 0
        self._sum = 0
        self._xor = 0

    def add(self, value: bytes) -> None:
        item = int.from_bytes(hashlib.sha256(value).digest(), "big")
        self._count += 1
        self._sum = (self._sum + item) % self._MODULUS
        self._xor ^= item

    def hexdigest(self) -> str:
        if self._count == 0:
            return hashlib.sha256(b"").hexdigest()
        canonical = (
            self._count.to_bytes(8, "big")
            + self._sum.to_bytes(32, "big")
            + self._xor.to_bytes(32, "big")
        )
        return hashlib.sha256(canonical).hexdigest()


def _projection_identity_from_payload(payload: dict[str, Any]) -> tuple[str, str, int]:
    resource_type = str(payload.get("resource_type") or "").strip()
    entity_type = str(payload.get("entity_type") or "").strip()
    resource_id = str(payload.get("resource_id") or payload.get("entity_id") or "").strip()
    partition_id = str(payload.get("retrieval_partition_id") or "").strip()
    version = payload.get("projection_version")
    source_kind = str(payload.get("source_kind") or "").strip()
    if resource_type != FILE_MANAGER_FILE_RESOURCE_TYPE:
        raise RuntimeError("Physical generation contains a non-Files resource")
    if entity_type and entity_type != "file":
        raise RuntimeError("Physical generation contains a non-Files entity")
    if source_kind and source_kind != "files":
        raise RuntimeError("Physical generation contains a non-Files source")
    if (
        not resource_id
        or not partition_id
        or isinstance(version, bool)
        or not isinstance(version, int)
        or version <= 0
    ):
        raise RuntimeError("Physical generation contains an unfenced Files projection")
    return resource_id, partition_id, version


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _qdrant_payload_schema_config(payload_schema: object) -> object:
    """Return only stable payload-index configuration from Qdrant metadata."""

    value = _jsonable(payload_schema)
    if not isinstance(value, dict):
        return value
    stable: dict[str, object] = {}
    for field_name, definition in value.items():
        if isinstance(definition, dict):
            stable[field_name] = {key: item for key, item in definition.items() if key != "points"}
        else:
            stable[field_name] = definition
    return stable


__all__ = ["FilesPhysicalGenerationBackends"]
