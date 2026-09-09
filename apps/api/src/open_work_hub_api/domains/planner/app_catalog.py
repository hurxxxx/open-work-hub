from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

PLANNER_APP = app_registration(
    "planner",
    nav_items=(
        AppNavRegistration(
            id="planner-calendar",
            title="캘린더",
            category="Schedule",
            icon_key="calendar",
        ),
        AppNavRegistration(
            id="planner-timeline",
            title="타임라인",
            category="Schedule",
            icon_key="activity",
            path_suffix="?view=timeline",
        ),
    ),
)
