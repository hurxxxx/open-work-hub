from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


PMS_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="pms",
    title="PMS",
    route_base="/pms",
    icon_key="folder-kanban",
    backend_domain="pms",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    launcher_pinned_by_default=True,
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
