from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

BENTO_APP = app_registration(
    "bento",
    nav_items=(
        AppNavRegistration(
            id="bento-all",
            title="All Presentations",
            category="Library",
            icon_key="presentation",
        ),
        AppNavRegistration(
            id="bento-mine",
            title="My Presentations",
            category="Library",
            icon_key="user",
        ),
        AppNavRegistration(
            id="bento-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
