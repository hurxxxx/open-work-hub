from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.ai.conversation_scope import conversation_scope_turn_context
from ai_do_api.core.db import get_engine
from ai_do_api.domains.ai import approvals as ai_approvals
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.conversations.default_scope_adapters import (
    ensure_conversation_scope_adapters_registered,
)
from ai_do_api.domains.conversations import service as conversations_service
from ai_do_api.domains.conversations.models import Conversation
from ai_do_api.domains.conversations.scope_registry import (
    ConversationExperience,
    register_conversation_scope_adapter,
    reset_conversation_scope_adapters,
)
from ai_do_api.platform_extensions import _validate_conversation_scope_registry_contracts
from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting


def _workspace_slug(client, token: str) -> str:
    response = client.get("/api/v1/admin/workspaces", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    workspace = response.json()[0]
    return workspace.get("slug", workspace["key"])


def _workspace_ai_conversations_path(workspace_slug: str, suffix: str = "") -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot/conversations{suffix}"


class _ExtensionConversationScopeAdapter:
    scope_ref = "external_plugin_record_scope"
    experience = ConversationExperience(owner_app_id="chatbot")

    def validate(self, **kwargs) -> None:
        del kwargs

    def system_prompt(self, **kwargs) -> str:
        del kwargs
        return "This conversation is scoped to an external plugin record."


class _MissingPromptConversationScopeAdapter:
    scope_ref = "missing_prompt_scope"
    experience = ConversationExperience(owner_app_id="chatbot")

    def validate(self, **kwargs) -> None:
        del kwargs

    def system_prompt(self, **kwargs) -> str:
        del kwargs
        return ""


class _CountingConversationScopeAdapter:
    scope_ref = "counting_scope"
    experience = ConversationExperience(owner_app_id="chatbot")

    def __init__(self) -> None:
        self.validate_calls = 0
        self.validated_resource_ids: list[str] = []

    def validate(self, **kwargs) -> None:
        self.validate_calls += 1
        self.validated_resource_ids.append(kwargs["scope_resource_id"])

    def system_prompt(self, **kwargs) -> str:
        del kwargs
        return "Scoped prompt."


class _UnboundConversationScopeAdapter:
    scope_ref = "unbound_scope"


class _DirectResponseConversationScopeAdapter:
    scope_ref = "direct_response_scope"
    experience = ConversationExperience(owner_app_id="chatbot")
    server_owned_artifact_types = frozenset({"plugin-analysis"})

    def validate(self, **kwargs) -> None:
        del kwargs

    def system_prompt(self, **kwargs) -> str:
        del kwargs
        return "Scoped prompt."

    def turn_context(self, **kwargs) -> dict:
        del kwargs
        return {
            "direct_response": "  fixed server response  ",
            "server_owned_artifact_types": ["turn-owned-artifact"],
        }


def test_conversation_scope_registration_requires_experience() -> None:
    reset_conversation_scope_adapters()
    try:
        with pytest.raises(ValueError, match="must declare an experience"):
            register_conversation_scope_adapter(_UnboundConversationScopeAdapter())
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()


def test_conversation_scope_registration_rejects_duplicate_artifact_owner() -> None:
    reset_conversation_scope_adapters()
    try:
        first = SimpleNamespace(
            scope_ref="first_scope",
            experience=ConversationExperience(owner_app_id="chatbot"),
            server_owned_artifact_types=frozenset({"owned-analysis"}),
        )
        second = SimpleNamespace(
            scope_ref="second_scope",
            experience=ConversationExperience(owner_app_id="chatbot"),
            server_owned_artifact_types=frozenset({"owned-analysis"}),
        )
        register_conversation_scope_adapter(first)

        with pytest.raises(ValueError, match="already owned"):
            register_conversation_scope_adapter(second)
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()


def test_conversation_scope_contract_rejects_unknown_owner_and_workload() -> None:
    reset_conversation_scope_adapters()
    try:
        register_conversation_scope_adapter(
            SimpleNamespace(
                scope_ref="plugin_scope",
                experience=ConversationExperience(
                    owner_app_id="plugin-app",
                    chat_workload_id="plugin.chat",
                ),
            )
        )

        problems = _validate_conversation_scope_registry_contracts()

        assert (
            "conversation scope owner app is not registered: plugin_scope -> plugin-app" in problems
        )
        assert (
            "conversation scope chat workload is not registered: plugin_scope -> plugin.chat"
            in problems
        )
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()


def test_create_ai_conversation_with_meeting_scope(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Scoped kickoff")

    response = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scopeRef"] == "meeting"
    assert body["scopeResourceId"] == meeting["id"]
    assert body["turns"] == []
    assert body["livePendingApproval"] is None


def test_create_ai_conversation_rejects_scope_adapter_without_prompt(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    reset_conversation_scope_adapters()
    try:
        ensure_conversation_scope_adapters_registered()
        register_conversation_scope_adapter(_MissingPromptConversationScopeAdapter())

        response = client.post(
            _workspace_ai_conversations_path(slug),
            headers=_auth_headers(token),
            json={
                "title": "",
                "scopeRef": _MissingPromptConversationScopeAdapter.scope_ref,
                "scopeResourceId": "plugin-record-1",
            },
        )
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()

    assert response.status_code == 500, response.text
    assert response.json()["code"] == "ai.conversation_scope_prompt_missing"


def test_existing_conversation_scope_is_revalidated_for_turn_context() -> None:
    adapter = _CountingConversationScopeAdapter()
    reset_conversation_scope_adapters()
    try:
        ensure_conversation_scope_adapters_registered()
        register_conversation_scope_adapter(adapter)

        context = conversation_scope_turn_context(
            SimpleNamespace(),
            workspace=SimpleNamespace(),
            principal=SimpleNamespace(),
            user=SimpleNamespace(),
            conversation=SimpleNamespace(
                scope_ref=adapter.scope_ref,
                scope_resource_id="record-1",
            ),
            messages=[],
        )
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()

    assert context.prompt == "Scoped prompt."
    assert adapter.validate_calls == 1
    assert adapter.validated_resource_ids == ["record-1"]


def test_turn_context_preserves_direct_response_and_owned_artifact_types() -> None:
    adapter = _DirectResponseConversationScopeAdapter()
    reset_conversation_scope_adapters()
    try:
        ensure_conversation_scope_adapters_registered()
        register_conversation_scope_adapter(adapter)

        context = conversation_scope_turn_context(
            SimpleNamespace(),
            workspace=SimpleNamespace(),
            principal=SimpleNamespace(),
            user=SimpleNamespace(),
            conversation=SimpleNamespace(
                scope_ref=adapter.scope_ref,
                scope_resource_id="record-1",
            ),
            messages=[],
        )
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()

    assert context.direct_response == "fixed server response"
    assert context.server_owned_artifact_types == frozenset(
        {"plugin-analysis", "turn-owned-artifact"}
    )


def test_create_conversation_preserves_extension_scope_resource_key(client) -> None:
    session = _bootstrap_admin_session(client)
    slug = _workspace_slug(client, session["token"])
    scope_resource_id = "external-system:project-alpha:record-" + ("x" * 64)

    reset_conversation_scope_adapters()
    try:
        ensure_conversation_scope_adapters_registered()
        register_conversation_scope_adapter(_ExtensionConversationScopeAdapter())
        with Session(get_engine()) as db:
            workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
            user = db.get(User, session["user"]["id"])
            assert workspace is not None
            assert user is not None

            conversation = conversations_service.create_conversation(
                db,
                workspace=workspace,
                user=user,
                title="",
                scope_ref=_ExtensionConversationScopeAdapter.scope_ref,
                scope_resource_id=scope_resource_id,
            )

            assert conversation.scope_ref == _ExtensionConversationScopeAdapter.scope_ref
            assert conversation.scope_resource_id == scope_resource_id
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()


def test_list_conversations_accepts_extension_scope_filter_lengths(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    scope_resource_id = "external-system:project-alpha:record-" + ("x" * 64)

    reset_conversation_scope_adapters()
    try:
        ensure_conversation_scope_adapters_registered()
        register_conversation_scope_adapter(_ExtensionConversationScopeAdapter())
        with Session(get_engine()) as db:
            workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
            user = db.get(User, session["user"]["id"])
            assert workspace is not None
            assert user is not None

            conversation = conversations_service.create_conversation(
                db,
                workspace=workspace,
                user=user,
                title="",
                scope_ref=_ExtensionConversationScopeAdapter.scope_ref,
                scope_resource_id=scope_resource_id,
            )

        response = client.get(
            _workspace_ai_conversations_path(slug),
            headers=_auth_headers(token),
            params={
                "scope_ref": _ExtensionConversationScopeAdapter.scope_ref,
                "scope_resource_id": scope_resource_id,
            },
        )

        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [conversation.id]
    finally:
        reset_conversation_scope_adapters()
        ensure_conversation_scope_adapters_registered()


def test_list_conversations_rejects_scope_resource_without_scope_ref(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    response = client.get(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        params={"scope_resource_id": "meeting-1"},
    )

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "conversations.scope_pair_required"


def test_get_ai_conversation_returns_live_pending_approval(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Approval scoped meeting")

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="",
            scope_ref="meeting",
            scope_resource_id=meeting["id"],
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "system", "content": "scoped"}],
            blocked_call_id="call-1",
            model_meta={"model": "test-model"},
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-1",
            tool_name="pms.create_task",
            arguments_json='{"title":"Fix scope"}',
            resource_preview="이슈 생성",
        )
        db.commit()
        conversation_id = conversation.id
        approval_id = approval.id
        snapshot_id = snapshot.id

    response = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conversation_id
    assert body["livePendingApproval"] is not None
    assert body["livePendingApproval"]["approvalId"] == approval_id
    assert body["livePendingApproval"]["agentRunId"] == snapshot_id
    assert body["livePendingApproval"]["callId"] == "call-1"
    assert body["livePendingApproval"]["tool"] == "pms.create_task"
    assert body["livePendingApproval"]["resourcePreview"] == "이슈 생성"
    assert body["livePendingApproval"]["status"] == "pending"
    assert body["livePendingApproval"]["reason"] is None
    assert isinstance(body["livePendingApproval"]["expiresAtMs"], int)


def test_get_ai_conversation_omits_terminal_live_pending_approval(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Expired approval meeting")

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="",
            scope_ref="meeting",
            scope_resource_id=meeting["id"],
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "system", "content": "scoped"}],
            blocked_call_id="call-expired",
            model_meta={"model": "test-model"},
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-expired",
            tool_name="pms.create_task",
            arguments_json='{"title":"Fix scope"}',
            resource_preview="이슈 생성",
        )
        approval.status = "expired"
        db.add(approval)
        db.commit()
        conversation_id = conversation.id

    response = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["livePendingApproval"] is None


def test_get_ai_conversation_lazy_expires_stale_pending_approval(
    client,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Lazy expire meeting")
    audit_calls: list[dict[str, object | None]] = []

    def _capture_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(ai_approvals, "log_llm_tool_approval_resolved", _capture_audit)

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="",
            scope_ref="meeting",
            scope_resource_id=meeting["id"],
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "system", "content": "scoped"}],
            blocked_call_id="call-expire-lazy",
            model_meta={"model": "test-model"},
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-expire-lazy",
            tool_name="pms.create_task",
            arguments_json='{"title":"Fix scope"}',
            resource_preview="이슈 생성",
            expires_at=ai_approvals.utcnow_naive() - timedelta(minutes=1),
        )
        db.commit()
        conversation_id = conversation.id
        approval_id = approval.id
        snapshot_id = snapshot.id

    response = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["livePendingApproval"] is None

    with Session(get_engine()) as db:
        approval = db.get(ai_approvals.AiToolApproval, approval_id)
        snapshot = db.get(ai_approvals.AgentRunSnapshot, snapshot_id)
        assert approval is not None
        assert snapshot is not None
        assert approval.status == "expired"
        assert snapshot.status == "abandoned"
    assert len(audit_calls) == 1
    assert audit_calls[0]["decision"] == "expired"
    assert audit_calls[0]["approval_id"] == approval_id


def test_create_ai_conversation_reuses_latest_empty_scoped_conversation(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Reuse scoped meeting")

    first = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]


def test_get_ai_conversation_tolerates_legacy_unsupported_scope_row(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, workspace_slug=slug, title="Legacy scope row")

    response = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert response.status_code == 201, response.text
    conversation_id = response.json()["id"]

    with Session(get_engine()) as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation is not None
        conversation.scope_ref = "docs_page"
        conversation.scope_resource_id = "doc-1"
        db.add(conversation)
        db.commit()

    detail = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["scopeRef"] is None
    assert body["scopeResourceId"] is None
