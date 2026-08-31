from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceNavRegistration,
    workspace_app_registration,
)


BENTO_WORKSPACE_APP = workspace_app_registration(
    "bento",
    nav_items=(
        WorkspaceNavRegistration(
            id="bento-all",
            title="All Presentations",
            category="Library",
            icon_key="presentation",
        ),
        WorkspaceNavRegistration(
            id="bento-mine",
            title="My Presentations",
            category="Library",
            icon_key="user",
        ),
        WorkspaceNavRegistration(
            id="bento-archived",
            title="Archived",
            category="Library",
            icon_key="history",
        ),
    ),
)
