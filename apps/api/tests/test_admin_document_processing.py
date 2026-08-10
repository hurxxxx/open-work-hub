from __future__ import annotations

from fastapi.testclient import TestClient

from open_work_hub_api.domains.admin import document_processing_projection
from tests.dev_accounts import auth_headers, dev_login


def _admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(dev_login(client)["token"])


def test_admin_document_processing_projects_read_only_runtime(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        document_processing_projection,
        "get_rag_runtime_health",
        lambda: {
            "enabled": True,
            "ready": False,
            "collection": "test-collection",
            "providers": [
                {"provider_name": "qdrant", "ready": True, "detail": "secret detail"},
                {
                    "provider_name": "inference-gateway-ocr",
                    "ready": False,
                    "detail": "internal runtime detail",
                },
            ],
        },
    )

    response = client.get(
        "/api/v1/admin/document-processing",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["configuration_scope"] == "api_environment"
    assert payload["health_scope"] == "api_process"
    assert payload["worker_health_available"] is False
    assert payload["ready"] is False
    assert payload["providers"] == [
        {"provider_name": "qdrant", "ready": True},
        {"provider_name": "inference-gateway-ocr", "ready": False},
    ]
    assert payload["chunking"]["strategy"] == "default_korean_v1"
    assert isinstance(payload["vision"]["workloads"], list)
    assert "api_key" not in response.text
    assert "secret detail" not in response.text
    assert "internal runtime detail" not in response.text


def test_admin_document_processing_requires_platform_admin(client: TestClient) -> None:
    headers = auth_headers(dev_login(client, "delivery-hub-member")["token"])

    response = client.get("/api/v1/admin/document-processing", headers=headers)

    assert response.status_code == 403
