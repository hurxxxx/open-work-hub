from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


MANAGEMENT_TASKS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="management-tasks",
    title="종합검진",
    route_base="/management-tasks",
    icon_key="activity",
    enabled_by_default=False,
    visible_by_default=False,
    availability_scope="workspace",
    launcher_category=True,
    coming_soon=False,
    platform_admin_activation_required=True,
    backend_domain="management_tasks",
    nav_items=(
        WorkspaceNavRegistration(
            id="health-checkup",
            title="종합검진 대상자 관리",
            category="nurse",
            icon_key="activity",
        ),
    ),
)
