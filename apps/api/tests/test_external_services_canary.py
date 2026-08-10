from __future__ import annotations

from io import BytesIO

import pytest

from integration_infra import IntegrationInfra, MinioTestTarget
from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client
from ai_do_api.domains.files.storage_adapter import (
    open_file_object,
    put_file_object,
    remove_file_object,
)
from ai_do_api.domains.search.opensearch import OpenSearchKeywordClient


pytestmark = pytest.mark.external_integration


def test_minio_file_storage_round_trip(
    monkeypatch: pytest.MonkeyPatch,
    minio_target: MinioTestTarget,
) -> None:
    payload = b"release validation minio canary"
    storage_key = "canary/round-trip.txt"
    monkeypatch.setenv("AI_DO_MINIO_ENDPOINT", minio_target.endpoint)
    monkeypatch.setenv("AI_DO_MINIO_ACCESS_KEY", minio_target.access_key)
    monkeypatch.setenv("AI_DO_MINIO_SECRET_KEY", minio_target.secret_key)
    monkeypatch.setenv("AI_DO_MINIO_BUCKET", minio_target.bucket)
    get_settings.cache_clear()
    get_minio_client.cache_clear()
    try:
        ensure_bucket()
        put_file_object(
            storage_key=storage_key,
            content=BytesIO(payload),
            size_bytes=len(payload),
            content_type="text/plain",
        )
        stored = open_file_object(storage_key)
        try:
            assert b"".join(stored.stream(8)) == payload
        finally:
            stored.close()
            stored.release_conn()
        remove_file_object(storage_key)
    finally:
        get_minio_client.cache_clear()
        get_settings.cache_clear()


def test_opensearch_keyword_client_round_trip(
    integration_infra: IntegrationInfra,
) -> None:
    index_prefix = integration_infra.new_opensearch_index_prefix()
    client = OpenSearchKeywordClient(
        base_url=integration_infra.opensearch_url,
        index_prefix=index_prefix,
    )
    document = {
        "workspace_id": "release-canary-workspace",
        "entity_type": "plugin_chunk",
        "entity_id": "release-canary-document",
        "title": "Release canary",
        "summary": "",
        "body": "external service round trip",
    }
    try:
        client.upsert_document(document)
        assert (
            client.count_workspace_documents(
                workspace_id=document["workspace_id"],
                entity_types=(document["entity_type"],),
            )
            == 1
        )
        client.delete_document(
            workspace_id=document["workspace_id"],
            entity_type=document["entity_type"],
            entity_id=document["entity_id"],
        )
        assert (
            client.count_workspace_documents(
                workspace_id=document["workspace_id"],
                entity_types=(document["entity_type"],),
            )
            == 0
        )
    finally:
        integration_infra.cleanup_opensearch_indices(index_prefix)
