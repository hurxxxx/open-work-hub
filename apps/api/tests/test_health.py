from fastapi.testclient import TestClient

from aidoo_api.main import app


client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_documents_search_scaffold() -> None:
    response = client.post(
        "/api/v1/search/documents",
        json={"query": "compressor specification"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario_id"] == "documents-rag"
    assert payload["hits"]
