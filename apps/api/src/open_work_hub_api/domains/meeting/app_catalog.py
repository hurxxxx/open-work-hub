from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

MEETING_APP = app_registration(
    "meeting",
    backend_domain="meeting",
    nav_items=(
        AppNavRegistration(
            id="meeting-upcoming",
            title="Upcoming",
            category="Meetings",
            icon_key="calendar",
        ),
        AppNavRegistration(
            id="meeting-mine",
            title="My Meetings",
            category="Meetings",
            icon_key="user",
            path_suffix="?scope=mine",
        ),
        AppNavRegistration(
            id="meeting-recordings",
            title="Recordings",
            category="Meetings",
            icon_key="video",
            path_suffix="?tab=recordings",
        ),
    ),
)
