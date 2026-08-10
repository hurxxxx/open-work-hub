from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PLANNER_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="planner",
    title="Planner",
    route_base="/planner",
    icon_key="calendar",
    availability_scope="platform",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=False,
    launcher_personal_tools=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="planner-calendar",
            title="캘린더",
            category="Schedule",
            icon_key="calendar",
        ),
        WorkspaceNavRegistration(
            id="planner-timeline",
            title="타임라인",
            category="Schedule",
            icon_key="activity",
            path_suffix="?view=timeline",
        ),
    ),
)
