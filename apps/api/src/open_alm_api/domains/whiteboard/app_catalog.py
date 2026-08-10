from open_alm_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


WHITEBOARD_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="whiteboard",
    title="WHITEBOARD",
    route_base="/whiteboard",
    icon_key="pencil-ruler",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    launcher_pinned_by_default=True,
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
