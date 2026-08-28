from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


MEETING_WORKSPACE_APP = workspace_app_registration(
    "meeting",
    backend_domain="meeting",
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
