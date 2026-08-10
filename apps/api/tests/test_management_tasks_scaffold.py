from __future__ import annotations

import pytest
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute

from ai_do_api.core.db import Base
from ai_do_api.domains.management_tasks import router as health_router
from ai_do_api.domains.management_tasks.app_catalog import MANAGEMENT_TASKS_WORKSPACE_APP
from ai_do_api.domains.management_tasks.xlsx import XLSX_MEDIA_TYPE


def test_app_is_ready_but_disabled_until_enabled_for_a_workspace() -> None:
    registration = MANAGEMENT_TASKS_WORKSPACE_APP

    assert registration.app_id == "management-tasks"
    assert registration.availability_scope == "workspace"
    assert registration.enabled_by_default is False
    assert registration.visible_by_default is False
    assert registration.coming_soon is False
    assert registration.platform_admin_activation_required is True
    assert {
        table_name
        for table_name in Base.metadata.tables
        if table_name.startswith("management_health_")
    } == {
        "management_health_checkup_settings",
        "management_health_checkup_settings_history",
        "management_health_decision_rows",
        "management_health_decision_runs",
        "management_health_prior_rows",
        "management_health_prior_uploads",
    }


def test_every_delivered_route_retains_activation_and_workspace_member_gates() -> None:
    for route in health_router.router.routes:
        assert isinstance(route, APIRoute)
        dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
        assert health_router.require_management_tasks_enabled in dependency_calls
        assert health_router.require_management_tasks_member in dependency_calls
@pytest.mark.parametrize(
    "endpoint",
    [
        health_router.export_employees,
        health_router.export_targets,
        health_router.export_roster,
    ],
)
def test_exports_declare_binary_xlsx_response_contract(endpoint: object) -> None:
    route = next(
        route
        for route in health_router.router.routes
        if getattr(route, "endpoint", None) is endpoint
    )

    assert isinstance(route, APIRoute)
    assert route.response_class is StreamingResponse
    assert route.responses[200]["content"] == {
        XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}
    }
