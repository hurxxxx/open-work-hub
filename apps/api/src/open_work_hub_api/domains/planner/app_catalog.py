from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


PLANNER_WORKSPACE_APP = workspace_app_registration(
    "planner",
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
