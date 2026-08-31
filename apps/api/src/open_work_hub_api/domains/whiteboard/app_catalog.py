from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


WHITEBOARD_WORKSPACE_APP = workspace_app_registration(
    "whiteboard",
    nav_items=(
        WorkspaceNavRegistration(
            id="whiteboard-all",
            title="All Whiteboards",
            category="Library",
            icon_key="pencil-ruler",
        ),
        WorkspaceNavRegistration(
            id="whiteboard-my",
            title="My Whiteboards",
            category="Library",
            icon_key="user",
        ),
        WorkspaceNavRegistration(
            id="whiteboard-recent",
            title="Recent",
            category="Library",
            icon_key="history",
        ),
        WorkspaceNavRegistration(
            id="whiteboard-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
