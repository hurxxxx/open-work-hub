from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

PMS_APP = app_registration(
    "pms",
    backend_domain="pms",
    nav_items=(
        AppNavRegistration(
            id="pms-inbox",
            title="Inbox",
            category="Personal",
            icon_key="inbox",
        ),
        AppNavRegistration(
            id="pms-tasks",
            title="My Tasks",
            category="Personal",
            icon_key="check-circle-2",
            path_suffix="/assigned",
        ),
        AppNavRegistration(
            id="pms-tasks-assigned",
            title="Assigned to me",
            category="Personal",
            icon_key="user",
            path_suffix="/assigned",
        ),
        AppNavRegistration(
            id="pms-tasks-today",
            title="Today & Overdue",
            category="Personal",
            icon_key="calendar",
            path_suffix="/today",
        ),
    ),
)
