from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from dev_accounts import create_workspace_user_session, dev_login

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai import router as ai_router
from ai_do_api.domains.auth.models import (
    PlatformAppVisibility,
    Workspace,
    WorkspaceAppEntitlement,
)
from ai_do_api.domains.writing_assistant import router as writing_assistant_router
from ai_do_api.domains.writing_assistant.schemas import WritingResult


@dataclass(frozen=True)
class _AppApiGateCase:
    app_id: str
    method: str
    path: str
    allowed_status: int
    json: dict[str, object] | None = None


_APP_API_GATE_CASES = (
    _AppApiGateCase("chatbot", "GET", "/chatbot/conversations", 200),
    _AppApiGateCase("docs", "GET", "/chatbot/apps/docs/manifest", 200),
    _AppApiGateCase("docs", "GET", "/docs/hub", 200),
    _AppApiGateCase("whiteboard", "GET", "/whiteboard/hub", 200),
    _AppApiGateCase("diagrams", "GET", "/diagrams/hub", 200),
    _AppApiGateCase("plm", "POST", "/search/plm", 422, {}),
    _AppApiGateCase("pms", "GET", "/pms/spaces", 200),
    _AppApiGateCase("meeting", "GET", "/meeting/meetings", 200),
    _AppApiGateCase("video-chat", "GET", "/video-chat/sessions", 200),
    _AppApiGateCase("recording", "GET", "/recording/recordings", 200),
    _AppApiGateCase("retrieval-search", "GET", "/retrieval/sources", 200),
    _AppApiGateCase("spec-compare", "GET", "/spec-compare/jobs", 200),
    _AppApiGateCase("law-search", "GET", "/lawsearch/parts", 200),
    _AppApiGateCase("patent-compose", "POST", "/patent/ai-search", 422, {}),
    _AppApiGateCase("patent-analysis", "POST", "/patent/translate", 200, {}),
    _AppApiGateCase("patent-analysis", "POST", "/patent/fetch", 422, {}),
    _AppApiGateCase("patent-automation", "GET", "/patent-automation/fields", 200),
    _AppApiGateCase("patent-prior-art", "GET", "/patent-prior-art/config", 200),
    _AppApiGateCase("meal-invoice-ocr", "GET", "/meal-invoice-ocr/catalog", 200),
    _AppApiGateCase("files", "GET", "/files", 200),
    _AppApiGateCase("legacy-issues", "GET", "/legacy-issues/org-units", 200),
    _AppApiGateCase("data-viz", "GET", "/dataviz/core-measurement/groups", 200),
    _AppApiGateCase("ppt-assistant", "GET", "/ppt-generator/families", 200),
    _AppApiGateCase("imds-minerals", "POST", "/imds-minerals/analyze", 422),
    _AppApiGateCase("document-translate", "POST", "/document-translate/process-text", 422, {}),
    _AppApiGateCase("fmea-compare", "POST", "/fmea-compare/ai-analyze", 400, {}),
    _AppApiGateCase("web-search", "POST", "/web-search/ask/stream", 422, {}),
    _AppApiGateCase("research-trends", "POST", "/research-trends/ask/stream", 422, {}),
    _AppApiGateCase("standards-monitor", "POST", "/standards-monitor/ask/stream", 422, {}),
)


def _auth_headers(client: TestClient) -> dict[str, str]:
    token = dev_login(client, "administrator")["token"]
    return {"Authorization": f"Bearer {token}"}


def _set_workspace_app_visibility(app_id: str, visible: bool) -> None:
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "ai-tft"))
        assert workspace is not None
        entitlement = db.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == app_id,
            )
        )
        assert entitlement is not None
        entitlement.visibility_override = visible
        db.add(entitlement)
        db.commit()


def _set_platform_app_visibility(app_id: str, visible: bool) -> None:
    with get_session_factory()() as db:
        visibility = db.scalar(
            select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == app_id)
        )
        assert visibility is not None
        visibility.visible = visible
        db.add(visibility)
        db.commit()


@pytest.mark.parametrize(
    "path",
    ("/api/v1/news/status", "/api/v1/industry-report/status"),
)
def test_news_platform_api_gate_blocks_direct_requests(
    client: TestClient,
    path: str,
) -> None:
    headers = _auth_headers(client)
    _set_platform_app_visibility("news", True)

    allowed = client.get(path, headers=headers)
    assert allowed.status_code == 200, allowed.text

    _set_platform_app_visibility("news", False)

    disabled = client.get(path, headers=headers)
    assert disabled.status_code == 403, disabled.text
    assert disabled.json()["code"] == "platform.app_disabled"


def test_qna_platform_api_gate_blocks_direct_requests(client: TestClient) -> None:
    headers = _auth_headers(client)
    _set_platform_app_visibility("qa-assistant", True)

    allowed = client.get("/api/v1/qna/notices", headers=headers)
    assert allowed.status_code == 200, allowed.text

    _set_platform_app_visibility("qa-assistant", False)

    disabled = client.get("/api/v1/qna/notices", headers=headers)
    assert disabled.status_code == 403, disabled.text
    assert disabled.json()["code"] == "platform.app_disabled"


def test_management_health_checkup_requires_workspace_membership_and_activation(
    client: TestClient,
) -> None:
    path = "/api/v1/workspaces/ai-tft/management-tasks/health-checkup/source/status"

    anonymous = client.get(path)
    assert anonymous.status_code == 401, anonymous.text

    member = create_workspace_user_session(
        client,
        workspace_key="ai-tft",
        login_id="management-task-member",
        email="management-task-member@ai-do.local",
        full_name="Management Task Member",
    )
    member_headers = {"Authorization": f"Bearer {member['token']}"}
    disabled = client.get(path, headers=member_headers)
    assert disabled.status_code == 403, disabled.text
    assert disabled.json()["code"] == "workspace.app_disabled"
    disabled_bootstrap = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers=member_headers,
    )
    assert disabled_bootstrap.status_code == 200, disabled_bootstrap.text
    assert "management-tasks" not in {
        item["app_id"] for item in disabled_bootstrap.json()["apps"]
    }

    nonmember = dev_login(client, "delivery-hub-member")
    nonmember_response = client.get(
        path,
        headers={"Authorization": f"Bearer {nonmember['token']}"},
    )
    assert nonmember_response.status_code == 403, nonmember_response.text
    assert nonmember_response.json()["code"] == "workspace.membership_required"

    _set_workspace_app_visibility("management-tasks", True)
    allowed = client.get(path, headers=member_headers)
    assert allowed.status_code == 200, allowed.text
    enabled_bootstrap = client.get(
        "/api/v1/workspaces/ai-tft/bootstrap",
        headers=member_headers,
    )
    assert enabled_bootstrap.status_code == 200, enabled_bootstrap.text
    enabled_payload = enabled_bootstrap.json()
    assert "management-tasks" in {item["app_id"] for item in enabled_payload["apps"]}
    assert {
        "id": "health-checkup",
        "app_id": "management-tasks",
        "path_suffix": None,
    }.items() <= next(
        item for item in enabled_payload["nav"] if item["id"] == "health-checkup"
    ).items()

    old_global_path = "/api/v1/management-tasks/health-checkup/source/status"
    assert client.get(old_global_path, headers=member_headers).status_code == 404
    _set_workspace_app_visibility("management-tasks", False)


@pytest.mark.parametrize(
    ("visible", "expected_disabled"),
    [(True, False), (False, True)],
    ids=["allowed", "disabled"],
)
def test_workspace_app_api_gate_matrix(
    client: TestClient,
    visible: bool,
    expected_disabled: bool,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft"

    for case in _APP_API_GATE_CASES:
        _set_workspace_app_visibility(case.app_id, visible)
        response = client.request(
            case.method,
            f"{base_path}{case.path}",
            headers=headers,
            json=case.json,
        )
        if expected_disabled:
            assert response.status_code == 403, (case.app_id, response.text)
            assert response.json()["code"].endswith("app_disabled"), case.app_id
        else:
            assert response.status_code == case.allowed_status, (case.app_id, response.text)


def test_workspace_override_allows_workspace_app_when_platform_default_is_hidden(
    client: TestClient,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft"
    _set_platform_app_visibility("legacy-issues", False)
    _set_workspace_app_visibility("legacy-issues", True)

    app_response = client.get(
        f"{base_path}/legacy-issues/org-units",
        headers=headers,
    )
    assert app_response.status_code == 200, app_response.text

    conversation_response = client.post(
        f"{base_path}/chatbot/conversations",
        headers=headers,
        json={
            "title": "",
            "scopeRef": "legacy_issues",
            "scopeResourceId": "workspace",
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text


def test_image_api_requires_enabled_image_wizard_app(
    client: TestClient,
    monkeypatch,
) -> None:
    headers = _auth_headers(client)
    path = "/api/v1/workspaces/ai-tft/images/generations"
    monkeypatch.setenv("AI_DO_IMAGE_ENABLED", "1")
    get_settings.cache_clear()

    allowed = client.get(path, headers=headers)
    assert allowed.status_code == 200, allowed.text

    _set_workspace_app_visibility("image-wizard", False)

    disabled = client.get(path, headers=headers)
    assert disabled.status_code == 403
    assert disabled.json()["code"] == "images.app_disabled"


@pytest.mark.parametrize("disabled_at", ["workspace", "platform"])
def test_scoped_conversation_surface_uses_owning_app_entitlement(
    client: TestClient,
    disabled_at: str,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/chatbot"
    if disabled_at == "workspace":
        _set_workspace_app_visibility("chatbot", False)
    else:
        _set_platform_app_visibility("chatbot", False)

    unscoped = client.get(f"{base_path}/conversations", headers=headers)
    assert unscoped.status_code == 403
    assert unscoped.json()["code"] == "workspace.app_disabled"

    created = client.post(
        f"{base_path}/conversations",
        headers=headers,
        json={
            "title": "",
            "scopeRef": "legacy_issues",
            "scopeResourceId": "workspace",
        },
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    scoped_list = client.get(
        f"{base_path}/conversations",
        headers=headers,
        params={
            "scope_ref": "legacy_issues",
            "scope_resource_id": "workspace",
        },
    )
    assert scoped_list.status_code == 200, scoped_list.text
    assert [item["id"] for item in scoped_list.json()["items"]] == [conversation_id]

    detail = client.get(
        f"{base_path}/conversations/{conversation_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["scopeRef"] == "legacy_issues"

    renamed = client.patch(
        f"{base_path}/conversations/{conversation_id}",
        headers=headers,
        json={"title": "과거차 분석"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "과거차 분석"

    _set_workspace_app_visibility("legacy-issues", False)
    owning_app_disabled = client.get(
        f"{base_path}/conversations/{conversation_id}",
        headers=headers,
    )
    assert owning_app_disabled.status_code == 403
    assert owning_app_disabled.json()["code"] == "workspace.app_disabled"
    rename_disabled = client.patch(
        f"{base_path}/conversations/{conversation_id}",
        headers=headers,
        json={"title": "차단되어야 함"},
    )
    assert rename_disabled.status_code == 403
    delete_disabled = client.delete(
        f"{base_path}/conversations/{conversation_id}",
        headers=headers,
    )
    assert delete_disabled.status_code == 403


@pytest.mark.parametrize("disabled_at", ["workspace", "platform"])
def test_scoped_chat_stream_uses_owning_app_entitlement(
    client: TestClient,
    monkeypatch,
    disabled_at: str,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/chatbot"
    captured_contexts = []
    captured_payloads = []
    if disabled_at == "workspace":
        _set_workspace_app_visibility("chatbot", False)
    else:
        _set_platform_app_visibility("chatbot", False)

    async def _stream(**kwargs):
        captured_contexts.append(kwargs["context"])
        captured_payloads.append(kwargs["payload"])
        yield {"event": "done", "data": '{"finish_reason":"stop"}'}

    monkeypatch.setattr(ai_router, "_chat_stream_publisher", _stream)

    unscoped = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={"messages": [{"role": "user", "content": "일반 질문"}]},
    )
    assert unscoped.status_code == 403
    assert unscoped.json()["code"] == "workspace.app_disabled"

    sync_scoped = client.post(
        f"{base_path}/chat",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "과거차 문제를 분석해줘"}],
            "persist": True,
            "scope_ref": "legacy_issues",
            "scope_resource_id": "workspace",
        },
    )
    assert sync_scoped.status_code == 409, sync_scoped.text
    assert sync_scoped.json()["code"] == "ai.durable_stream_required"

    scoped = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "과거차 문제를 분석해줘"}],
            "persist": True,
            "scope_ref": "legacy_issues",
            "scope_resource_id": "workspace",
        },
    )
    assert scoped.status_code == 200, scoped.text
    assert len(captured_contexts) == 1
    assert len(captured_payloads) == 1
    assert captured_payloads[0].persist is True
    assert captured_payloads[0].scope_ref == "legacy_issues"
    assert captured_payloads[0].scope_resource_id == "workspace"
    assert captured_contexts[0].app_id == "legacy-issues"
    assert captured_contexts[0].task_kind == "legacy_issue_conversation_answer"
    assert captured_contexts[0].workload_id == "legacy_issues.conversation_answer"


def test_scoped_chat_stream_uses_stored_owning_app_experience(
    client: TestClient,
    monkeypatch,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/chatbot"
    captured_contexts = []

    async def _stream(**kwargs):
        captured_contexts.append(kwargs["context"])
        yield {"event": "done", "data": '{"finish_reason":"stop"}'}

    monkeypatch.setattr(ai_router, "_chat_stream_publisher", _stream)
    _set_workspace_app_visibility("chatbot", False)

    created = client.post(
        f"{base_path}/conversations",
        headers=headers,
        json={
            "title": "",
            "scopeRef": "legacy_issues",
            "scopeResourceId": "workspace",
        },
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]

    fresh = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "fresh"}],
            "scope_ref": "legacy_issues",
            "scope_resource_id": "workspace",
        },
    )
    assert fresh.status_code == 200, fresh.text

    follow_up = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "follow up"}],
            "conversation_id": conversation_id,
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    assert [context.app_id for context in captured_contexts] == [
        "legacy-issues",
        "legacy-issues",
    ]
    assert [context.task_kind for context in captured_contexts] == [
        "legacy_issue_conversation_answer",
        "legacy_issue_conversation_answer",
    ]
    assert [context.workload_id for context in captured_contexts] == [
        "legacy_issues.conversation_answer",
        "legacy_issues.conversation_answer",
    ]

    _set_workspace_app_visibility("legacy-issues", False)
    blocked_fresh = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "blocked fresh"}],
            "scope_ref": "legacy_issues",
            "scope_resource_id": "workspace",
        },
    )
    assert blocked_fresh.status_code == 403
    blocked_existing = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "blocked existing"}],
            "conversation_id": conversation_id,
        },
    )
    assert blocked_existing.status_code == 403


def test_files_scoped_chat_uses_files_entitlement_and_workload(
    client: TestClient,
    monkeypatch,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/chatbot"
    captured_contexts = []
    captured_payloads = []

    async def _stream(**kwargs):
        captured_contexts.append(kwargs["context"])
        captured_payloads.append(kwargs["payload"])
        yield {"event": "done", "data": '{"finish_reason":"stop"}'}

    monkeypatch.setattr(ai_router, "_chat_stream_publisher", _stream)
    _set_workspace_app_visibility("files", True)
    _set_workspace_app_visibility("chatbot", False)

    nonpersisted = client.post(
        f"{base_path}/chat",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "저장하지 않고 답해줘"}],
            "scope_ref": "files",
            "scope_resource_id": "workspace",
            "persist": False,
        },
    )
    assert nonpersisted.status_code == 400
    assert nonpersisted.json()["code"] == "ai.conversation_persistence_required"
    nonpersisted_stream = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "스트림도 저장하지 않아"}],
            "scope_ref": "files",
            "scope_resource_id": "workspace",
            "persist": False,
        },
    )
    assert nonpersisted_stream.status_code == 400
    assert nonpersisted_stream.json()["code"] == "ai.conversation_persistence_required"

    created = client.post(
        f"{base_path}/conversations",
        headers=headers,
        json={
            "title": "",
            "scopeRef": "files",
            "scopeResourceId": "workspace",
        },
    )
    assert created.status_code == 201, created.text

    scoped = client.post(
        f"{base_path}/chat/stream",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": "저장된 문서에서 찾아줘"}],
            "conversation_id": created.json()["id"],
            "allowed_app_ids": ["pms"],
        },
    )
    assert scoped.status_code == 200, scoped.text
    assert len(captured_contexts) == 1
    assert len(captured_payloads) == 1
    assert captured_contexts[0].app_id == "files"
    assert captured_contexts[0].task_kind == "files_grounded_chat"
    assert captured_contexts[0].workload_id == "files.grounded_chat"
    assert captured_payloads[0].allowed_app_ids == []

    tool_command = client.post(
        f"{base_path}/chat",
        headers=headers,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": '/tool pms.search_tasks {"q":"strict boundary"}',
                }
            ],
            "conversation_id": created.json()["id"],
            "allowed_app_ids": ["pms"],
        },
    )
    assert tool_command.status_code == 403
    assert tool_command.json()["code"] == "ai.chat_context_tool_not_allowed"

    _set_workspace_app_visibility("files", False)
    blocked = client.get(
        f"{base_path}/conversations/{created.json()['id']}",
        headers=headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "workspace.app_disabled"


def test_generic_chat_rejects_persistence_only_conversation_scope(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/workspaces/ai-tft/chatbot/chat",
        headers=_auth_headers(client),
        json={
            "messages": [{"role": "user", "content": "Q&A scope로 일반 채팅"}],
            "scope_ref": "qna_assistant",
            "scope_resource_id": "company",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ai.unsupported_conversation_scope"


def test_generic_chat_rejects_unregistered_fresh_conversation_scope(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/workspaces/ai-tft/chatbot/chat",
        headers=_auth_headers(client),
        json={
            "messages": [{"role": "user", "content": "등록되지 않은 scope"}],
            "scope_ref": "unknown_extension_scope",
            "scope_resource_id": "record-1",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "ai.unsupported_conversation_scope"


def test_unfiltered_chatbot_history_hides_disabled_scope_owners(
    client: TestClient,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/chatbot/conversations"
    unscoped = client.post(base_path, headers=headers, json={"title": "일반 대화"})
    assert unscoped.status_code == 201, unscoped.text
    scoped = client.post(
        base_path,
        headers=headers,
        json={
            "title": "과거차 대화",
            "scopeRef": "legacy_issues",
            "scopeResourceId": "workspace",
        },
    )
    assert scoped.status_code == 201, scoped.text

    _set_workspace_app_visibility("legacy-issues", False)
    response = client.get(base_path, headers=headers)

    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [unscoped.json()["id"]]


def test_writing_assistant_operations_require_their_owning_app(
    client: TestClient,
    monkeypatch,
) -> None:
    headers = _auth_headers(client)
    base_path = "/api/v1/workspaces/ai-tft/writing-assistant"
    monkeypatch.setattr(
        writing_assistant_router.service,
        "generate_draft",
        lambda *_args, **_kwargs: WritingResult(result="draft-ok"),
    )
    monkeypatch.setattr(
        writing_assistant_router.service,
        "generate_mail",
        lambda *_args, **_kwargs: WritingResult(result="mail-ok"),
    )
    monkeypatch.setattr(
        writing_assistant_router.service,
        "translate",
        lambda *_args, **_kwargs: WritingResult(result="translate-ok"),
    )

    draft_allowed = client.post(
        f"{base_path}/draft/generate",
        headers=headers,
        json={"text": "draft input", "type": "general", "lang": "ko"},
    )
    assert draft_allowed.status_code == 200, draft_allowed.text
    templates_allowed = client.get(
        "/api/v1/workspaces/ai-tft/templates",
        headers=headers,
    )
    assert templates_allowed.status_code == 200, templates_allowed.text

    _set_workspace_app_visibility("drafting", False)

    draft_disabled = client.post(
        f"{base_path}/draft/generate",
        headers=headers,
        json={"text": "draft input", "type": "general", "lang": "ko"},
    )
    assert draft_disabled.status_code == 403
    assert draft_disabled.json()["code"] == "writing_assistant.app_disabled"
    templates_disabled = client.get(
        "/api/v1/workspaces/ai-tft/templates",
        headers=headers,
    )
    assert templates_disabled.status_code == 403
    assert templates_disabled.json()["code"] == "writing_assistant.app_disabled"

    mail_allowed = client.post(
        f"{base_path}/mail/generate",
        headers=headers,
        json={"intent": "reply", "original_mail": "", "tone": "polite", "lang": "ko"},
    )
    assert mail_allowed.status_code == 200, mail_allowed.text

    _set_workspace_app_visibility("email-assistant", False)

    mail_disabled = client.post(
        f"{base_path}/mail/generate",
        headers=headers,
        json={"intent": "reply", "original_mail": "", "tone": "polite", "lang": "ko"},
    )
    assert mail_disabled.status_code == 403
    assert mail_disabled.json()["code"] == "writing_assistant.app_disabled"

    shared_disabled = client.post(
        f"{base_path}/translate",
        headers=headers,
        json={"source": "hello", "target_lang": "ko"},
    )
    assert shared_disabled.status_code == 403
    assert shared_disabled.json()["code"] == "writing_assistant.app_disabled"

    _set_workspace_app_visibility("email-assistant", True)

    shared_allowed = client.post(
        f"{base_path}/translate",
        headers=headers,
        json={"source": "hello", "target_lang": "ko"},
    )
    assert shared_allowed.status_code == 200, shared_allowed.text
