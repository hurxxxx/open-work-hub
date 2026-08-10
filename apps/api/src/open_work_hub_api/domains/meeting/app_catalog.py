from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


MEETING_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="meeting",
    title="MEETING",
    route_base="/meeting",
    icon_key="users",
    backend_domain="meeting",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="meeting-upcoming",
            title="Upcoming",
            category="Meetings",
            icon_key="calendar",
        ),
        WorkspaceNavRegistration(
            id="meeting-mine",
            title="My Meetings",
            category="Meetings",
            icon_key="user",
            path_suffix="?scope=mine",
        ),
        WorkspaceNavRegistration(
            id="meeting-recordings",
            title="Recordings",
            category="Meetings",
            icon_key="video",
            path_suffix="?tab=recordings",
        ),
    ),
)
