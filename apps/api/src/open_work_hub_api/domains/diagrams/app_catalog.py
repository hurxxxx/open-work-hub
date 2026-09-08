from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

DIAGRAMS_APP = app_registration(
    "diagrams",
    nav_items=(
        AppNavRegistration(
            id="diagrams-all",
            title="All Diagrams",
            category="Library",
            icon_key="workflow",
        ),
        AppNavRegistration(
            id="diagrams-mine",
            title="My Diagrams",
            category="Library",
            icon_key="user",
            path_suffix="?view=mine",
        ),
        AppNavRegistration(
            id="diagrams-archived",
            title="Archived",
            category="Library",
            icon_key="archive",
            path_suffix="?view=archived",
        ),
    ),
)
