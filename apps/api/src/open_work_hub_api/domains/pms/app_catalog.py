from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


PMS_WORKSPACE_APP = workspace_app_registration(
    "pms",
    backend_domain="pms",
    nav_items=(
        WorkspaceNavRegistration(
            id="pms-inbox",
            title="Inbox",
            category="Personal",
            icon_key="inbox",
        ),
        WorkspaceNavRegistration(
            id="pms-tasks",
            title="My Tasks",
            category="Personal",
            icon_key="check-circle-2",
            path_suffix="/assigned",
        ),
        WorkspaceNavRegistration(
            id="pms-tasks-assigned",
            title="Assigned to me",
            category="Personal",
            icon_key="user",
            path_suffix="/assigned",
        ),
        WorkspaceNavRegistration(
            id="pms-tasks-today",
            title="Today & Overdue",
            category="Personal",
            icon_key="calendar",
            path_suffix="/today",
        ),
    ),
)
