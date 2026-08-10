from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from dev_accounts import dev_login

from ai_do_api.core.db import get_engine, get_session_factory
from ai_do_api.core.principal import CallerPrincipal, user_principal
from ai_do_api.domains.ai.registry import get_ai_capability_registry
from ai_do_api.domains.ai.tool_surface import (
    resolve_agent_tool_surface,
    resolve_filtered_capability_tools,
)
from ai_do_api.domains.auth.access import load_user_graph
from ai_do_api.domains.auth.models import (
    PlatformAppVisibility,
    Workspace,
)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _load_workspace_principal(session: dict) -> tuple[Workspace, CallerPrincipal]:
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        user = load_user_graph(db, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="api.stream",
        )
        db.expunge(workspace)
        return workspace, principal


def _disable_platform_app(app_id: str) -> None:
    with Session(get_engine()) as db:
        visibility = db.scalar(
            select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == app_id)
        )
        assert visibility is not None
        visibility.visible = False
        db.add(visibility)
        db.commit()


def test_agent_tool_surface_empty_scope_disables_all_tools(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    workspace, principal = _load_workspace_principal(session)

    with get_session_factory()() as db:
        surface = resolve_agent_tool_surface(
            db,
            workspace=workspace,
            principal=principal,
            messages=[{"role": "user", "content": "hi"}],
            allowed_app_ids=[],
        )

    assert surface.tool_specs == []
    assert surface.capability_tools == []
    assert surface.tool_names == []
    assert surface.approval_required_tool_names == []
    assert surface.has_approval_required_tools is False


def test_agent_tool_surface_exposes_provider_neutral_tool_metadata(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    workspace, principal = _load_workspace_principal(session)

    with get_session_factory()() as db:
        surface = resolve_agent_tool_surface(
            db,
            workspace=workspace,
            principal=principal,
            messages=[{"role": "user", "content": "문서 근거를 찾아줘"}],
            allowed_app_ids=["chatbot"],
        )

    contract_names = sorted(spec.name for spec in surface.tool_specs)
    assert surface.tool_names == contract_names
    assert all(spec.description for spec in surface.tool_specs)
    assert all(spec.input_schema.get("type") == "object" for spec in surface.tool_specs)
    assert set(surface.approval_required_tool_names) <= set(surface.tool_names)
    assert surface.has_approval_required_tools == bool(surface.approval_required_tool_names)


def test_agent_tool_surface_uses_scope_not_message_keywords_for_rag(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    workspace, principal = _load_workspace_principal(session)

    with get_session_factory()() as db:
        surface = resolve_agent_tool_surface(
            db,
            workspace=workspace,
            principal=principal,
            messages=[{"role": "user", "content": "안녕하세요"}],
            allowed_app_ids=["chatbot"],
        )

    assert "rag.query" in surface.tool_names
    assert "rag.list_sources" in surface.tool_names
    assert "retrieval.search" in surface.tool_names
    assert "retrieval.list_sources" in surface.tool_names


def test_filtered_capability_tools_intersect_app_scope_with_platform_visibility(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    workspace, principal = _load_workspace_principal(session)
    _disable_platform_app("planner")

    with get_session_factory()() as db:
        tools = resolve_filtered_capability_tools(
            db,
            registry=get_ai_capability_registry(),
            workspace=workspace,
            principal=principal,
            app_ids=["planner"],
        )

    assert tools == []


def test_agent_tool_surface_hides_disabled_platform_apps_in_legacy_openai_path(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    workspace, principal = _load_workspace_principal(session)
    _disable_platform_app("planner")

    with get_session_factory()() as db:
        surface = resolve_agent_tool_surface(
            db,
            workspace=workspace,
            principal=principal,
            messages=[{"role": "user", "content": "계획을 정리해줘"}],
        )

    registry = get_ai_capability_registry()
    surfaced_app_ids = {
        registry.descriptors[name].workspace_app_id
        for name in surface.tool_names
        if name in registry.descriptors
    }
    assert "planner" not in surfaced_app_ids
