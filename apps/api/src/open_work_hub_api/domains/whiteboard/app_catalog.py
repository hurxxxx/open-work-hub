from open_work_hub_api.core.app_registry import (
    AppNavRegistration,
    app_registration,
)

WHITEBOARD_APP = app_registration(
    "whiteboard",
    nav_items=(
        AppNavRegistration(
            id="whiteboard-all",
            title="All Whiteboards",
            category="Library",
            icon_key="pencil-ruler",
        ),
        AppNavRegistration(
            id="whiteboard-my",
            title="My Whiteboards",
            category="Library",
            icon_key="user",
        ),
        AppNavRegistration(
            id="whiteboard-recent",
            title="Recent",
            category="Library",
            icon_key="history",
        ),
        AppNavRegistration(
            id="whiteboard-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
