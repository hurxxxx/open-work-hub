from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from dev_accounts import dev_login
from open_work_hub_api.core.llm import LlmCompletionResult, LlmToolCall
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.bento import (
    BENTO_EDIT_WORKLOAD_ID,
    BENTO_GENERATE_WORKLOAD_ID,
)
from open_work_hub_api.domains.bento import generation as bento_generation


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _document_json(*, title: str, slide_id: str = "slide-1") -> str:
    return json.dumps(
        {
            "format": "bento/slides",
            "version": 1,
            "docId": "doc-1",
            "title": title,
            "size": {"width": 1280, "height": 720},
            "theme": {
                "background": "#FFFFFF",
                "color": "#1E2A3A",
                "accent": "#F7A600",
                "fontFamily": "sans-serif",
            },
            "slides": [
                {
                    "id": slide_id,
                    "background": "#FFFFFF",
                    "transition": "fade",
                    "elements": [],
                    "notes": "",
                }
            ],
            "modified": "2026-08-11T00:00:00Z",
        }
    )


def _generated_document(*, title: str, slide_count: int) -> str:
    return json.dumps(
        {
            "format": "bento/slides",
            "version": 1,
            "docId": "model-controlled-doc-id",
            "title": title,
            "size": {"width": 1280, "height": 720},
            "theme": {
                "background": "#101418",
                "color": "#F2F0EA",
                "accent": "#FF9E8A",
                "fontFamily": "system-ui, sans-serif",
            },
            "slides": [
                {
                    "id": f"slide-{index + 1:02d}",
                    "background": "#101418",
                    "transition": "fade",
                    "notes": f"Speaker guidance for slide {index + 1}",
                    "elements": [
                        {
                            "id": f"title-{index + 1:02d}",
                            "type": "text",
                            "x": 96,
                            "y": 96,
                            "w": 1088,
                            "h": 120,
                            "rotation": 0,
                            "opacity": 1,
                            "html": f"Slide {index + 1}",
                            "fontSize": 64,
                            "fontFamily": "system-ui, sans-serif",
                            "fontWeight": 700,
                            "color": "#F2F0EA",
                            "align": "left",
                            "valign": "top",
                            "lineHeight": 1.1,
                        }
                    ],
                }
                for index in range(slide_count)
            ],
            "modified": "2026-08-11T00:00:00Z",
        }
    )


def _tool_completion(document_json: str) -> LlmCompletionResult:
    return LlmCompletionResult(
        text="",
        model="local/qwen",
        finish_reason="tool_calls",
        tool_calls=(
            LlmToolCall(
                id="call-1",
                name="submit_bento_document",
                arguments=json.dumps({"document_json": document_json}),
            ),
        ),
    )


def test_bento_model_normalizer_supplies_title_and_normalizes_percent_opacity() -> None:
    document = json.loads(_generated_document(title="discarded", slide_count=1))
    document.pop("title")
    element = document["slides"][0]["elements"][0]
    document["slides"][0]["speakerNotes"] = document["slides"][0].pop("notes")
    element["opacity"] = 85
    element["html"] = (
        "<h1 style='font-size:64px'>Title</h1><div><strong>Bold</strong> and <em>italic</em></div>"
    )

    normalized = bento_generation._normalize_model_response(
        json.dumps(document),
        expected_slide_count=1,
        document_id=None,
        preserved_document=None,
        fallback_title="Fallback brief",
    )

    assert normalized["title"] == "Fallback brief"
    assert normalized["slides"][0]["notes"] == "Speaker guidance for slide 1"
    normalized_element = normalized["slides"][0]["elements"][0]
    assert normalized_element["opacity"] == 0.85
    assert normalized_element["html"] == (
        "<span style='font-size:64px'>Title</span><br><span><b>Bold</b> and <i>italic</i></span>"
    )

    normalized_shape = bento_generation._normalize_element(
        {
            "id": "accent",
            "type": "shape",
            "x": 96,
            "y": 300,
            "w": 200,
            "h": 8,
            "rotation": 0,
            "opacity": 100,
            "shape": "rect",
            "fill": "#F7A600",
            "stroke": "",
            "strokeWidth": 0,
            "radius": 4,
        }
    )
    assert normalized_shape["stroke"] == "transparent"


def test_bento_create_update_archive_restore_and_delete(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(session["token"])
    base = "/api/v1/workspaces/delivery-hub/bento"

    create_response = client.post(
        f"{base}/items",
        headers=headers,
        json={"title": "Launch deck"},
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["title"] == "Launch deck"
    assert created["visibility"] == "personal"
    assert created["version"] == 1
    assert json.loads(created["document_json"])["format"] == "bento/slides"

    stale_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={"version": 99, "title": "Stale"},
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "bento.version_conflict"

    update_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={
            "version": created["version"],
            "document_json": _document_json(title="Launch deck v2", slide_id="slide-2"),
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["title"] == "Launch deck v2"
    assert updated["version"] == 2
    assert json.loads(updated["document_json"])["slides"][0]["id"] == "slide-2"

    visibility_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={"version": updated["version"], "visibility": "workspace"},
    )
    assert visibility_response.status_code == 200, visibility_response.text
    visible = visibility_response.json()
    assert visible["visibility"] == "workspace"
    assert visible["version"] == 3

    archive_response = client.delete(f"{base}/items/{created['id']}", headers=headers)
    assert archive_response.status_code == 204

    archived_response = client.get(
        f"{base}/hub",
        headers=headers,
        params={"view": "archived"},
    )
    assert archived_response.status_code == 200
    assert [item["id"] for item in archived_response.json()["items"]] == [created["id"]]

    restore_response = client.post(
        f"{base}/items/{created['id']}/restore",
        headers=headers,
    )
    assert restore_response.status_code == 200, restore_response.text
    assert restore_response.json()["archived_at"] is None

    assert client.delete(f"{base}/items/{created['id']}", headers=headers).status_code == 204
    permanent_response = client.delete(
        f"{base}/items/{created['id']}/permanent",
        headers=headers,
    )
    assert permanent_response.status_code == 204
    assert client.get(f"{base}/items/{created['id']}", headers=headers).status_code == 404


def test_bento_visibility_and_workspace_access(client: TestClient) -> None:
    owner = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    base = "/api/v1/workspaces/delivery-hub/bento"

    personal_response = client.post(
        f"{base}/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Private deck"},
    )
    assert personal_response.status_code == 201, personal_response.text
    personal = personal_response.json()

    workspace_response = client.post(
        f"{base}/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Shared deck", "visibility": "workspace"},
    )
    assert workspace_response.status_code == 201, workspace_response.text
    workspace_document = workspace_response.json()

    member_hub_response = client.get(
        f"{base}/hub",
        headers=_auth_headers(member["token"]),
    )
    assert member_hub_response.status_code == 200
    member_ids = [item["id"] for item in member_hub_response.json()["items"]]
    assert workspace_document["id"] in member_ids
    assert personal["id"] not in member_ids

    assert (
        client.get(
            f"{base}/items/{personal['id']}",
            headers=_auth_headers(member["token"]),
        ).status_code
        == 404
    )

    member_update = client.patch(
        f"{base}/items/{workspace_document['id']}",
        headers=_auth_headers(member["token"]),
        json={
            "version": workspace_document["version"],
            "document_json": _document_json(title="Shared deck edited"),
        },
    )
    assert member_update.status_code == 200, member_update.text

    member_visibility = client.patch(
        f"{base}/items/{workspace_document['id']}",
        headers=_auth_headers(member["token"]),
        json={"version": member_update.json()["version"], "visibility": "personal"},
    )
    assert member_visibility.status_code == 403

    member_owned_response = client.post(
        f"{base}/items",
        headers=_auth_headers(member["token"]),
        json={"title": "Member deck", "visibility": "workspace"},
    )
    assert member_owned_response.status_code == 201, member_owned_response.text
    member_owned = member_owned_response.json()

    admin_visibility = client.patch(
        f"{base}/items/{member_owned['id']}",
        headers=_auth_headers(owner["token"]),
        json={"version": member_owned["version"], "visibility": "personal"},
    )
    assert admin_visibility.status_code == 200, admin_visibility.text
    assert admin_visibility.json()["visibility"] == "personal"
    assert (
        client.get(
            f"{base}/items/{member_owned['id']}",
            headers=_auth_headers(owner["token"]),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{base}/items/{member_owned['id']}",
            headers=_auth_headers(member["token"]),
        ).status_code
        == 200
    )

    no_membership = client.get(
        "/api/v1/workspaces/general/bento/hub",
        headers=_auth_headers(member["token"]),
    )
    assert no_membership.status_code == 403


def test_bento_rejects_invalid_document_payload(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items",
        headers=_auth_headers(session["token"]),
        json={"title": "Bad deck", "document_json": '{"format":"unknown"}'},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bento.invalid_document"

    blank_title_response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items",
        headers=_auth_headers(session["token"]),
        json={"title": "   ", "document_json": _document_json(title="Imported")},
    )
    assert blank_title_response.status_code == 422


def test_bento_ai_generation_uses_registered_local_workload_and_persists_document(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_execute(workload_id, context, db, **kwargs):
        del db
        captured.update(
            workload_id=workload_id,
            context=context,
            messages=kwargs["messages"],
            reasoning_effort=kwargs["reasoning_effort"],
            max_tokens=kwargs["max_tokens"],
            tools=kwargs["tools"],
            tool_choice=kwargs["tool_choice"],
            parallel_tool_calls=kwargs["parallel_tool_calls"],
        )
        return SimpleNamespace(
            completion=_tool_completion(_generated_document(title="AI launch plan", slide_count=4))
        )

    monkeypatch.setattr(bento_generation, "execute_llm", fake_execute)
    session = dev_login(client, "delivery-hub-admin")
    response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items/generate",
        headers=_auth_headers(session["token"]),
        json={
            "prompt": "신제품 출시 제안서를 작성해줘",
            "slide_count": 4,
            "language": "ko",
            "visibility": "workspace",
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    document = json.loads(created["document_json"])
    assert created["title"] == "AI launch plan"
    assert created["visibility"] == "workspace"
    assert document["docId"] != "model-controlled-doc-id"
    assert len(document["slides"]) == 4
    title_elements = [slide["elements"][0] for slide in document["slides"]]
    assert {element["role"] for element in title_elements} == {"title"}
    assert {element["morphId"] for element in title_elements} == {"bento-running-title"}
    assert captured["workload_id"] == BENTO_GENERATE_WORKLOAD_ID
    assert captured["reasoning_effort"] == "none"
    assert captured["max_tokens"] == 32_768
    assert captured["context"].app_id == "bento"
    assert captured["tools"][0]["function"]["name"] == "submit_bento_document"
    assert captured["tool_choice"]["function"]["name"] == "submit_bento_document"
    assert captured["parallel_tool_calls"] is False
    system_message = captured["messages"][0]
    assert "Morph is Bento's signature" in system_message["content"]
    assert "Two columns: x=96 and 656" in system_message["content"]
    user_message = captured["messages"][1]
    assert json.loads(user_message["content"])["brief"] == "신제품 출시 제안서를 작성해줘"


def test_bento_ai_generation_rejects_invalid_model_output_without_creating_document(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_calls = 0

    def fake_invalid_execute(*_args, **_kwargs):
        nonlocal model_calls
        model_calls += 1
        return SimpleNamespace(completion=LlmCompletionResult(text="not JSON", model="local/qwen"))

    monkeypatch.setattr(bento_generation, "execute_llm", fake_invalid_execute)
    session = dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(session["token"])
    base = "/api/v1/workspaces/delivery-hub/bento"
    before = client.get(f"{base}/hub", headers=headers).json()["total"]

    response = client.post(
        f"{base}/items/generate",
        headers=headers,
        json={"prompt": "invalid output test", "slide_count": 3},
    )

    assert response.status_code == 502
    assert response.json()["code"] == "bento.ai_invalid_response"
    assert model_calls == 2
    after = client.get(f"{base}/hub", headers=headers).json()["total"]
    assert after == before


def test_bento_ai_generation_repairs_invalid_model_output_once(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_responses = iter(
        [
            "not JSON",
            _generated_document(title="Repaired deck", slide_count=3),
        ]
    )
    calls: list[dict[str, object]] = []

    def fake_execute(workload_id, context, db, **kwargs):
        del db
        calls.append(
            {
                "workload_id": workload_id,
                "context": context,
                "messages": kwargs["messages"],
                "tools": kwargs["tools"],
            }
        )
        return SimpleNamespace(completion=_tool_completion(next(model_responses)))

    monkeypatch.setattr(bento_generation, "execute_llm", fake_execute)
    session = dev_login(client, "delivery-hub-admin")
    response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items/generate",
        headers=_auth_headers(session["token"]),
        json={"prompt": "repair this output", "slide_count": 3},
    )

    assert response.status_code == 201, response.text
    assert response.json()["title"] == "Repaired deck"
    assert len(calls) == 2
    assert calls[0]["workload_id"] == BENTO_GENERATE_WORKLOAD_ID
    assert calls[1]["workload_id"] == BENTO_GENERATE_WORKLOAD_ID
    assert calls[1]["context"].source == "api.bento.generate.repair"
    repair_payload = json.loads(calls[1]["messages"][1]["content"])
    assert repair_payload["invalid_model_response"] == "not JSON"
    assert repair_payload["required_slide_count"] == 3


def test_bento_ai_edit_preserves_document_identity_and_server_owned_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_execute(workload_id, context, db, **kwargs):
        del db
        captured.update(
            workload_id=workload_id,
            context=context,
            messages=kwargs["messages"],
        )
        return SimpleNamespace(
            completion=LlmCompletionResult(
                text=_generated_document(title="Revised launch plan", slide_count=1),
                model="local/qwen",
            )
        )

    monkeypatch.setattr(bento_generation, "execute_llm", fake_execute)
    current_document = json.loads(_generated_document(title="Original", slide_count=1))
    current_document["docId"] = "stable-document-id"
    current_document["collab"] = {"room": "private-room", "key": "never-send-this"}
    current_document["slides"][0]["comments"] = [
        {"id": "comment-1", "author": "Reviewer", "text": "Keep this", "at": "now"}
    ]

    session = dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(session["token"])
    base = "/api/v1/workspaces/delivery-hub/bento"
    created_response = client.post(
        f"{base}/items",
        headers=headers,
        json={
            "title": "Original",
            "document_json": json.dumps(current_document),
        },
    )
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()

    response = client.post(
        f"{base}/items/{created['id']}/ai-edit",
        headers=headers,
        json={
            "version": created["version"],
            "prompt": "문장을 더 간결하게 수정해줘",
            "language": "ko",
        },
    )

    assert response.status_code == 200, response.text
    revised = response.json()
    revised_document = json.loads(revised["document_json"])
    assert revised["id"] == created["id"]
    assert revised["version"] == created["version"] + 1
    assert revised["title"] == "Revised launch plan"
    assert revised_document["docId"] == "stable-document-id"
    assert revised_document["collab"] == current_document["collab"]
    assert revised_document["slides"][0]["comments"] == current_document["slides"][0]["comments"]
    assert captured["workload_id"] == BENTO_EDIT_WORKLOAD_ID
    model_payload = json.loads(captured["messages"][1]["content"])
    assert model_payload["revision_instruction"] == "문장을 더 간결하게 수정해줘"
    assert "collab" not in model_payload["current_document"]
    assert "comments" not in model_payload["current_document"]["slides"][0]
    title_element = revised_document["slides"][0]["elements"][0]
    assert title_element["role"] == "title"
    assert title_element["morphId"] == "bento-running-title"


def test_bento_ai_normalizer_downgrades_morph_without_a_real_partner() -> None:
    document = json.loads(_generated_document(title="No fake morph", slide_count=2))
    for index, slide in enumerate(document["slides"]):
        element = slide["elements"][0]
        element["id"] = f"body-{index + 1:02d}"
        element["fontSize"] = 24
        element["y"] = 300
    document["slides"][1]["transition"] = "morph"

    normalized = bento_generation._normalize_generated_document(
        document,
        expected_slide_count=2,
    )

    assert normalized["slides"][0]["elements"][0]["role"] == "body"
    assert normalized["slides"][1]["transition"] == "fade"


def test_bento_ai_edit_rejects_stale_version_before_model_call(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_execute(*_args, **_kwargs):
        raise AssertionError("model must not run for a stale document")

    monkeypatch.setattr(bento_generation, "execute_llm", fail_execute)
    session = dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(session["token"])
    base = "/api/v1/workspaces/delivery-hub/bento"
    created = client.post(
        f"{base}/items",
        headers=headers,
        json={
            "title": "Original",
            "document_json": _generated_document(title="Original", slide_count=1),
        },
    ).json()

    response = client.post(
        f"{base}/items/{created['id']}/ai-edit",
        headers=headers,
        json={"version": 99, "prompt": "수정해줘", "language": "ko"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "bento.version_conflict"


@pytest.mark.parametrize(
    "workload_id",
    [BENTO_EDIT_WORKLOAD_ID, BENTO_GENERATE_WORKLOAD_ID],
)
def test_bento_ai_workloads_are_registered_local_only(workload_id: str) -> None:
    workload = get_ai_capability_registry().resolve_llm_workload(workload_id)

    assert workload.app_ids == ("bento",)
    assert workload.default_route == "local"
    assert workload.allowed_routes == ("local",)
    assert workload.local_max_output_tokens == 32_768
